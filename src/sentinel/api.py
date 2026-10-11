"""Versioned HTTP API and simple multi-camera monitor."""
from __future__ import annotations

import hmac
import json
import os
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from time import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .domain import Camera, Detection, Kind, Rule, Zone
from .service import MonitorService
from .video import CaptureController, OpenCvZooYoloXDetector, YoloOnnxDetector


class DetectionInput(BaseModel):
    kind: Kind
    box: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1)
    activity: float = Field(default=0, ge=0, le=1)


class ObservationInput(BaseModel):
    at: float | None = None
    detections: list[DetectionInput]


class ZoneInput(BaseModel):
    id: str = Field(min_length=1)
    rule: Rule
    polygon: list[tuple[float, float]] = Field(min_length=3)
    dwell_seconds: float = Field(default=10, ge=0)
    cooldown_seconds: float = Field(default=30, ge=0)
    activity_threshold: float = Field(default=0.7, ge=0, le=1)
    min_vertical_travel: float = Field(default=0.12, gt=0, le=1)
    min_activity_samples: int = Field(default=2, ge=1)
    crossing_line_y: float | None = Field(default=None, gt=0, lt=1)


def public_track(track) -> dict[str, object]:
    result = asdict(track)
    for internal in ("zone_lowest_anchor", "upward_steps", "activity_samples", "crossed_lines"):
        result.pop(internal)
    return result


def create_app(config_path: str | None = None, api_key: str | None = None) -> FastAPI:
    service = MonitorService()
    config_file = config_path or os.getenv("SENTINEL_CONFIG")
    config = None
    if config_file:
        config = json.loads(Path(config_file).read_text(encoding="utf-8"))
        for item in config.get("cameras", []):
            source = item["source"]
            if isinstance(source, bool) or not isinstance(source, (str, int)) or (isinstance(source, int) and source < 0):
                raise ValueError("camera source must be a nonnegative webcam index or video source string")
            zones = tuple(Zone(zone["id"], Rule(zone["rule"]), tuple(tuple(point) for point in zone["polygon"]),
                               zone.get("dwell_seconds", 10), zone.get("cooldown_seconds", 30),
                               zone.get("activity_threshold", 0.7), zone.get("min_vertical_travel", 0.12),
                               zone.get("min_activity_samples", 2), zone.get("crossing_line_y")) for zone in item.get("zones", []))
            service.add_camera(Camera(item["id"], item["name"], source, zones))

    secret = api_key if api_key is not None else os.getenv("SENTINEL_API_KEY")
    if not secret:
        raise RuntimeError("SENTINEL_API_KEY is required")

    def detector_factory():
        model = Path(os.getenv("SENTINEL_ONNX_MODEL") or Path(__file__).resolve().parents[2] / "models" / "object_detection_yolox_2022nov.onnx")
        if not model.is_file():
            raise FileNotFoundError(f"detector model missing: {model}")
        detector_kind = os.getenv("SENTINEL_DETECTOR", "yolox")
        if detector_kind == "yolox":
            return OpenCvZooYoloXDetector(str(model))
        if detector_kind == "yolov8":
            return YoloOnnxDetector(str(model))
        raise ValueError("SENTINEL_DETECTOR must be yolox or yolov8")

    controller = CaptureController(service, detector_factory)
    config_lock = asyncio.Lock()

    async def authorize(x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key or not hmac.compare_digest(x_api_key, secret):
            raise HTTPException(status_code=401, detail="invalid API key")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await asyncio.to_thread(controller.stop_all)

    app = FastAPI(title="Township Sentinel", version="0.1.0", lifespan=lifespan)
    app.state.service = service
    app.state.controller = controller

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/cameras", dependencies=[Depends(authorize)])
    async def cameras():
        return [{"id": camera.id, "name": camera.name, "source_type": "synthetic" if camera.source == "synthetic" else "video",
                 "zones": [asdict(zone) for zone in camera.zones]} for camera in service.cameras()]

    @app.put("/api/v1/cameras/{camera_id}/zones", dependencies=[Depends(authorize)])
    async def update_zones(camera_id: str, payload: list[ZoneInput]):
        if config is None or config_file is None:
            raise HTTPException(status_code=409, detail="start with SENTINEL_CONFIG to save zones")
        try:
            zones = tuple(Zone(item.id, item.rule, tuple(item.polygon), item.dwell_seconds,
                               item.cooldown_seconds, item.activity_threshold, item.min_vertical_travel,
                               item.min_activity_samples, item.crossing_line_y) for item in payload)
            if len({zone.id for zone in zones}) != len(zones):
                raise ValueError("zone ids must be unique per camera")
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        async with config_lock:
            if camera_id not in {camera.id for camera in service.cameras()}:
                raise HTTPException(status_code=404, detail="camera not found")
            target = Path(config_file)
            if target.name.endswith(".example.json"):
                target = target.with_name("config.local.json")
            updated = json.loads(json.dumps(config))
            next(item for item in updated["cameras"] if item["id"] == camera_id)["zones"] = [
                item.model_dump(mode="json") for item in payload]
            temporary = target.with_suffix(target.suffix + ".tmp")
            try:
                temporary.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                os.replace(temporary, target)
            except OSError:
                temporary.unlink(missing_ok=True)
                raise HTTPException(status_code=503, detail="could not save camera zones")
            config.clear()
            config.update(updated)
            service.set_zones(camera_id, zones)
            return {"zones": [asdict(zone) for zone in zones], "saved_to": target.name}

    @app.get("/api/v1/cameras/{camera_id}/tracks", dependencies=[Depends(authorize)])
    async def tracks(camera_id: str):
        try:
            return [public_track(track) for track in service.tracks(camera_id)]
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")

    @app.get("/api/v1/cameras/{camera_id}/status", dependencies=[Depends(authorize)])
    async def camera_status(camera_id: str):
        try:
            status = service.status(camera_id)
            tracks_now = service.tracks(camera_id)
            return {**status, "person_count": sum(track.kind == Kind.PERSON for track in tracks_now),
                    "vehicle_count": sum(track.kind == Kind.VEHICLE for track in tracks_now)}
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")

    @app.post("/api/v1/cameras/{camera_id}/start", dependencies=[Depends(authorize)])
    async def start_camera(camera_id: str):
        try:
            return await asyncio.to_thread(controller.start, camera_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=422, detail=str(error))

    @app.post("/api/v1/cameras/{camera_id}/stop", dependencies=[Depends(authorize)])
    async def stop_camera(camera_id: str):
        try:
            return await asyncio.to_thread(controller.stop, camera_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error))

    @app.post("/api/v1/cameras/{camera_id}/observations", dependencies=[Depends(authorize)])
    async def observe(camera_id: str, payload: ObservationInput):
        try:
            detections = [Detection(item.kind, item.box, item.confidence, item.activity) for item in payload.detections]
            tracks, events = service.observe(camera_id, detections, payload.at if payload.at is not None else time())
            return {"tracks": [public_track(track) for track in tracks], "events": [asdict(event) for event in events]}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")

    @app.get("/api/v1/events", dependencies=[Depends(authorize)])
    async def events(camera_id: str | None = None):
        return [asdict(event) for event in service.events(camera_id)]

    @app.get("/api/v1/detections", dependencies=[Depends(authorize)])
    async def recent_detections(camera_id: str | None = None):
        return [asdict(item) for item in service.detections(camera_id)]

    @app.get("/api/v1/cameras/{camera_id}/snapshot", dependencies=[Depends(authorize)])
    async def snapshot(camera_id: str):
        try:
            frame = service.frame(camera_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")
        if frame is None:
            raise HTTPException(status_code=503, detail="frame unavailable")
        return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/cameras/{camera_id}/stream", dependencies=[Depends(authorize)])
    async def stream(camera_id: str):
        try:
            frame = service.frame(camera_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")
        if frame is None:
            raise HTTPException(status_code=503, detail="frame unavailable")

        async def frames():
            while True:
                if service.status(camera_id)["state"] == "stopped":
                    break
                frame = service.frame(camera_id)
                if frame:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")

    return app


def run() -> None:
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("SENTINEL_PORT", "8000")), access_log=False)


if __name__ == "__main__":
    run()
