"""Versioned HTTP API and routed management console."""
from __future__ import annotations

import asyncio
import hmac
import os
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path
from time import time
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .algorithm_test import AlgorithmTestRunner
from .alerts import AlertService
from .domain import Camera, Detection, Kind, Rule, Zone, MapPosition
from .settings import AnalysisSettings, JsonSettingsStore
from .service import MonitorService
from .storage import JsonCameraRepository, JsonStateStore
from .video import CaptureController
from .smolvlm import SmolVLM2Analyzer, MODEL_ID
from .vision import VisionAnalyzer
from .tracking import CentroidTracker
from .capabilities import CAPABILITIES


class FindingOutput(BaseModel):
    description: str
    model: str
    revision: str
    start_seconds: float
    end_seconds: float
    frames_analyzed: int
    review_required: bool
    danger_status: Literal["yes", "no", "uncertain"] = "uncertain"
    id: str | None = None
    camera_id: str | None = None
    observed_at: str | None = None


class AnalysisJobOutput(BaseModel):
    id: str
    filename: str
    state: Literal["queued", "running", "completed", "failed"]
    mode: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    findings: list[FindingOutput] = Field(default_factory=list)
    frames_processed: int
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class DetectionInput(BaseModel):
    kind: Kind
    box: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1)
    activity: float = Field(default=0, ge=0, le=1)


class ObservationInput(BaseModel):
    at: float | None = None
    detections: list[DetectionInput]


class ZoneInput(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    rule: Rule
    polygon: list[tuple[float, float]] = Field(min_length=3)
    dwell_seconds: float = Field(default=10, ge=0)
    cooldown_seconds: float = Field(default=30, ge=0)
    activity_threshold: float = Field(default=0.7, ge=0, le=1)
    min_vertical_travel: float = Field(default=0.12, gt=0, le=1)
    min_activity_samples: int = Field(default=2, ge=1)
    crossing_line_y: float | None = Field(default=None, gt=0, lt=1)
    meaning: str = Field(default="custom", min_length=1, max_length=80)
    min_count: int = Field(default=5, ge=2, le=1000, strict=True)
    stationary_tolerance: float = Field(default=0.025, gt=0, le=0.25)
    proximity_radius: float = Field(default=0.15, gt=0, le=1)


class MapPositionInput(BaseModel):
    x: float = Field(ge=-80, le=80, allow_inf_nan=False)
    y: float = Field(ge=-55, le=55, allow_inf_nan=False)


class AlertUpdate(BaseModel):
    status: Literal["pending", "resolved"]


class AlertOutput(BaseModel):
    id: str
    finding_id: str
    camera_id: str | None
    camera_name: str | None
    map_position: MapPositionInput | None
    source: Literal["camera", "media_job"]
    job_id: str | None
    description: str
    model: str
    revision: str
    start_seconds: float
    end_seconds: float
    frames_analyzed: int
    review_required: bool
    status: Literal["pending", "resolved"]
    created_at: str
    updated_at: str
    resolved_at: str | None


class CameraInput(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    source: str | int
    map_position: MapPositionInput | None = None

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | int) -> str | int:
        if isinstance(value, bool) or (isinstance(value, int) and value < 0):
            raise ValueError("source must be a nonnegative webcam index or video source string")
        if isinstance(value, str) and (not value.strip() or len(value) > 2048):
            raise ValueError("source must be between 1 and 2048 characters")
        return value


class CameraUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str | int | None = None
    map_position: MapPositionInput | None = None

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | int | None) -> str | int | None:
        return value if value is None else CameraInput.validate_source(value)


def public_track(track) -> dict[str, object]:
    result = asdict(track)
    for internal in ("zone_lowest_anchor", "upward_steps", "activity_samples", "crossed_lines", "stationary_anchor"):
        result.pop(internal)
    return result


def _source_label(source: str | int) -> str:
    if isinstance(source, int):
        return f"Webcam {source}"
    if source == "synthetic":
        return "Synthetic input"
    if source.lower().startswith("rtsp"):
        return "RTSP camera"
    if source.lower().startswith(("http://", "https://")):
        return "Network stream"
    return Path(source).name or "Video source"


def _public_camera(camera: Camera) -> dict[str, object]:
    source_type = "synthetic" if camera.source == "synthetic" else "webcam" if isinstance(camera.source, int) else "video"
    return {
        "id": camera.id,
        "name": camera.name,
        "source_type": source_type,
        "source_label": _source_label(camera.source),
        "zones": [asdict(zone) for zone in camera.zones],
        "map_position": asdict(camera.map_position) if camera.map_position else None,
    }


def create_app(config_path: str | None = None, api_key: str | None = None,
               data_path: str | None = None, analyzer: VisionAnalyzer | None = None) -> FastAPI:
    project_root = Path(__file__).resolve().parents[2]
    config_value = config_path or os.getenv("SENTINEL_CONFIG")
    config_source = Path(config_value) if config_value else project_root / "data" / "cameras.json"
    config_target = (config_source.with_name("config.local.json")
                     if config_source.name.endswith(".example.json") else config_source)
    camera_repository = JsonCameraRepository(config_source, config_target)

    state_value = data_path or os.getenv("SENTINEL_DATA_FILE")
    state_path = Path(state_value) if state_value else project_root / "data" / "sentinel-state.json"
    state_store = JsonStateStore(state_path)
    alert_service = AlertService(state_store)
    tracker_kind = "disabled"
    inference_fps = 0.5
    tracker_factory = CentroidTracker
    service = MonitorService(event_store=state_store, tracker_factory=tracker_factory, finding_store=state_store,
                             on_finding=alert_service.record_finding)
    for camera in camera_repository.load():
        service.add_camera(camera)

    secret = api_key if api_key is not None else os.getenv("SENTINEL_API_KEY")
    if not secret:
        raise RuntimeError("SENTINEL_API_KEY is required")

    settings_store = JsonSettingsStore(state_path.with_name(state_path.stem + "-settings.json"))
    admin_secret = os.getenv("SENTINEL_ADMIN_API_KEY") or secret
    vision_analyzer = analyzer or SmolVLM2Analyzer(settings_provider=settings_store.get)

    def analyzer_factory():
        return vision_analyzer

    controller = CaptureController(service, analyzer_factory, settings_provider=settings_store.get)
    algorithm_runner = AlgorithmTestRunner(analyzer_factory, state_store, state_path.parent / "algorithm-results",
                                          inference_fps=inference_fps, settings_provider=settings_store.get,
                                          on_finding=alert_service.record_finding)
    config_lock = asyncio.Lock()

    async def authorize(x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key or not hmac.compare_digest(x_api_key, secret):
            raise HTTPException(status_code=401, detail="invalid API key")

    async def authorize_admin(x_admin_key: str | None = Header(default=None),
                              x_api_key: str | None = Header(default=None)) -> None:
        candidate = x_admin_key or x_api_key
        if not candidate or not hmac.compare_digest(candidate, admin_secret):
            raise HTTPException(status_code=403, detail="admin key required")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        try:
            await asyncio.to_thread(controller.stop_all)
        finally:
            await asyncio.to_thread(algorithm_runner.close)

    app = FastAPI(title="Township Sentinel", version="0.3.0", lifespan=lifespan)
    app.state.service = service
    app.state.controller = controller
    app.state.algorithm_runner = algorithm_runner
    app.state.alert_service = alert_service

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/settings", response_model=AnalysisSettings,
             dependencies=[Depends(authorize), Depends(authorize_admin)])
    async def get_settings():
        return settings_store.get()

    @app.put("/api/v1/settings", response_model=AnalysisSettings,
             dependencies=[Depends(authorize), Depends(authorize_admin)])
    async def save_settings(payload: AnalysisSettings):
        try:
            await asyncio.to_thread(settings_store.save, payload)
        except OSError:
            raise HTTPException(status_code=503, detail="could not save analysis settings")
        return payload

    @app.post("/api/v1/session", dependencies=[Depends(authorize)])
    async def create_session():
        return {"authenticated": True}

    @app.get("/api/v1/summary", dependencies=[Depends(authorize)])
    async def summary():
        states = [service.status(camera.id) for camera in service.cameras()]
        return {
            "camera_count": len(states),
            "online_count": sum(item["state"] in {"starting", "running"} for item in states),
            "alert_count": len(alert_service.list("pending")),
            "detection_count": 0,
            "finding_count": len(service.findings()),
            "algorithm_test_count": len(algorithm_runner.list()),
        }

    @app.get("/api/v1/cameras", dependencies=[Depends(authorize)])
    async def cameras():
        return [_public_camera(camera) for camera in service.cameras()]

    @app.get("/api/v1/capabilities", dependencies=[Depends(authorize)])
    async def capabilities():
        return {"items": CAPABILITIES, "tracker": tracker_kind, "inference_fps": settings_store.get().sample_fps,
                "test_duration_limit_seconds": 60, "model": MODEL_ID, "automatic_alerts": True,
                "alert_review_required": True}

    @app.get("/api/v1/alerts", response_model=list[AlertOutput], dependencies=[Depends(authorize)])
    async def list_alerts(status: Literal["pending", "resolved"] | None = None):
        try:
            return await asyncio.to_thread(alert_service.list, status)
        except OSError:
            raise HTTPException(status_code=503, detail="could not read alerts")

    @app.patch("/api/v1/alerts/{alert_id}", response_model=AlertOutput, dependencies=[Depends(authorize)])
    async def update_alert(alert_id: str, payload: AlertUpdate):
        try:
            return await asyncio.to_thread(alert_service.set_status, alert_id, payload.status)
        except KeyError:
            raise HTTPException(status_code=404, detail="alert not found")
        except OSError:
            raise HTTPException(status_code=503, detail="could not save alert status")

    @app.get("/api/v1/cameras/{camera_id}", dependencies=[Depends(authorize)])
    async def camera_detail(camera_id: str):
        camera = next((item for item in service.cameras() if item.id == camera_id), None)
        if camera is None:
            raise HTTPException(status_code=404, detail="camera not found")
        return _public_camera(camera)

    @app.post("/api/v1/cameras", status_code=status.HTTP_201_CREATED, dependencies=[Depends(authorize)])
    async def create_camera(payload: CameraInput):
        camera = Camera(payload.id, payload.name.strip(), payload.source,
                        map_position=MapPosition(**payload.map_position.model_dump()) if payload.map_position else None)
        async with config_lock:
            current = service.cameras()
            if any(item.id == camera.id for item in current):
                raise HTTPException(status_code=409, detail="camera id already exists")
            try:
                camera_repository.save([*current, camera])
            except OSError:
                raise HTTPException(status_code=503, detail="could not save camera configuration")
            service.add_camera(camera)
        return _public_camera(camera)

    @app.put("/api/v1/cameras/{camera_id}", dependencies=[Depends(authorize)])
    async def update_camera(camera_id: str, payload: CameraUpdate):
        current = next((item for item in service.cameras() if item.id == camera_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail="camera not found")
        await asyncio.to_thread(controller.stop, camera_id)
        updated = replace(current, name=payload.name.strip(),
                          source=current.source if payload.source is None else payload.source,
                          map_position=(MapPosition(**payload.map_position.model_dump()) if payload.map_position else None)
                          if "map_position" in payload.model_fields_set else current.map_position)
        async with config_lock:
            proposed = [updated if item.id == camera_id else item for item in service.cameras()]
            try:
                camera_repository.save(proposed)
            except OSError:
                raise HTTPException(status_code=503, detail="could not save camera configuration")
            service.update_camera(camera_id, updated)
        return _public_camera(updated)

    @app.delete("/api/v1/cameras/{camera_id}", status_code=status.HTTP_204_NO_CONTENT,
                dependencies=[Depends(authorize)])
    async def delete_camera(camera_id: str):
        if not any(item.id == camera_id for item in service.cameras()):
            raise HTTPException(status_code=404, detail="camera not found")
        await asyncio.to_thread(controller.stop, camera_id)
        async with config_lock:
            proposed = [item for item in service.cameras() if item.id != camera_id]
            try:
                camera_repository.save(proposed)
            except OSError:
                raise HTTPException(status_code=503, detail="could not save camera configuration")
            service.remove_camera(camera_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.put("/api/v1/cameras/{camera_id}/zones", dependencies=[Depends(authorize)])
    async def update_zones(camera_id: str, payload: list[ZoneInput]):
        current = next((item for item in service.cameras() if item.id == camera_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail="camera not found")
        try:
            zones = tuple(Zone(item.id, item.rule, tuple(item.polygon), item.dwell_seconds,
                               item.cooldown_seconds, item.activity_threshold, item.min_vertical_travel,
                               item.min_activity_samples, item.crossing_line_y, item.meaning.strip(),
                               item.min_count, item.stationary_tolerance, item.proximity_radius) for item in payload)
            if len({zone.id for zone in zones}) != len(zones):
                raise ValueError("zone ids must be unique per camera")
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        updated = replace(current, zones=zones)
        async with config_lock:
            proposed = [updated if item.id == camera_id else item for item in service.cameras()]
            try:
                camera_repository.save(proposed)
            except OSError:
                raise HTTPException(status_code=503, detail="could not save camera zones")
            service.set_zones(camera_id, zones)
        return {"zones": [asdict(zone) for zone in zones], "saved_to": config_target.name}

    @app.get("/api/v1/cameras/{camera_id}/tracks", dependencies=[Depends(authorize)])
    async def tracks(camera_id: str):
        try:
            return [public_track(track) for track in service.tracks(camera_id)]
        except KeyError:
            raise HTTPException(status_code=404, detail="camera not found")

    @app.get("/api/v1/cameras/{camera_id}/status", dependencies=[Depends(authorize)])
    async def camera_status(camera_id: str):
        try:
            camera_state = service.status(camera_id)
            return {**camera_state, "person_count": None, "vehicle_count": None, "tracking_supported": False}
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

    @app.post("/api/v1/cameras/{camera_id}/observations", deprecated=True, dependencies=[Depends(authorize)])
    async def observe(camera_id: str, payload: ObservationInput):
        raise HTTPException(status_code=410, detail="Object observations are retired. Use the visual analysis API.")

    @app.get("/api/v1/findings", response_model=list[FindingOutput], response_model_exclude_none=True,
             dependencies=[Depends(authorize)])
    async def findings(camera_id: str | None = None):
        if camera_id and not any(camera.id == camera_id for camera in service.cameras()):
            raise HTTPException(status_code=404, detail="camera not found")
        return service.findings(camera_id)

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
                current_frame = service.frame(camera_id)
                if current_frame:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + current_frame + b"\r\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.post("/api/v1/analysis-jobs", status_code=status.HTTP_202_ACCEPTED,
              response_model=AnalysisJobOutput, response_model_exclude_none=True, dependencies=[Depends(authorize)])
    @app.post("/api/v1/algorithm-tests", status_code=status.HTTP_202_ACCEPTED,
              dependencies=[Depends(authorize)])
    async def create_algorithm_test(request: Request, x_filename: str | None = Header(default=None),
                                    camera_id: str | None = None):
        if not x_filename:
            raise HTTPException(status_code=422, detail="X-Filename header is required")
        camera = next((item for item in service.cameras() if item.id == camera_id), None) if camera_id else None
        if camera_id and camera is None:
            raise HTTPException(status_code=404, detail="camera not found")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > 100 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="file exceeds the 100 MB limit")
            payload.extend(chunk)
        if not payload:
            raise HTTPException(status_code=422, detail="file is empty")
        if len(payload) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="file exceeds the 100 MB limit")
        try:
            return await asyncio.to_thread(algorithm_runner.submit, x_filename,
                request.headers.get("content-type", "application/octet-stream"), bytes(payload), camera)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        except RuntimeError as error:
            raise HTTPException(status_code=429, detail=str(error))

    @app.get("/api/v1/algorithm-tests", dependencies=[Depends(authorize)])
    async def algorithm_tests():
        return algorithm_runner.list()

    @app.get("/api/v1/analysis-jobs/{test_id}", response_model=AnalysisJobOutput,
             response_model_exclude_none=True, dependencies=[Depends(authorize)])
    @app.get("/api/v1/algorithm-tests/{test_id}", dependencies=[Depends(authorize)])
    async def algorithm_test(test_id: str):
        try:
            return algorithm_runner.get(test_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="algorithm test not found")

    @app.get("/api/v1/analysis-jobs/{test_id}/result", dependencies=[Depends(authorize)])
    @app.get("/api/v1/algorithm-tests/{test_id}/result", dependencies=[Depends(authorize)])
    async def algorithm_test_result(test_id: str):
        try:
            path, media_type = await asyncio.to_thread(algorithm_runner.result, test_id)
            return FileResponse(path, media_type=media_type, filename=path.name,
                                headers={"Cache-Control": "private, no-store"})
        except KeyError:
            raise HTTPException(status_code=404, detail="algorithm test not found")
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error))
        except FileNotFoundError as error:
            raise HTTPException(status_code=410, detail=str(error))

    web_directory = Path(__file__).with_name("web")
    app.mount("/static", StaticFiles(directory=web_directory), name="static")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/login", status_code=307)

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login():
        return HTMLResponse((web_directory / "login.html").read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store"})

    @app.get("/{page_name}", response_class=HTMLResponse, include_in_schema=False)
    async def console_page(page_name: str):
        if page_name not in {"dashboard", "cameras", "robots", "map", "alerts", "algorithm-test", "settings"}:
            raise HTTPException(status_code=404, detail="page not found")
        return HTMLResponse((web_directory / "app.html").read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store"})

    @app.get("/cameras/{camera_id}", response_class=HTMLResponse, include_in_schema=False)
    async def camera_page(camera_id: str):
        if not any(camera.id == camera_id for camera in service.cameras()):
            raise HTTPException(status_code=404, detail="camera not found")
        return HTMLResponse((web_directory / "app.html").read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store"})

    return app


def run() -> None:
    import uvicorn
    logging.basicConfig(level=os.getenv("SENTINEL_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("sentinel").info("Starting local console; model=SmolVLM2 preview=%s FPS sample_interval=0.5s",
                                     os.getenv("SENTINEL_PREVIEW_FPS", "5"))
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("SENTINEL_PORT", "8000")), access_log=False)


if __name__ == "__main__":
    run()
