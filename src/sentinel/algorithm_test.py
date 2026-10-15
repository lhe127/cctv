"""Background image/video evaluation using the same visual-analysis contract as cameras."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event as StopEvent, RLock
from typing import Callable
from uuid import uuid4
import logging

from .domain import Camera
from .storage import JsonStateStore
from .vision import VisionAnalyzer
from .vision_session import VisionSession
from .webm import WebMWriter


SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_VIDEOS = {".mp4", ".mov", ".avi", ".mkv"}
logger = logging.getLogger("sentinel.algorithm")


class AlgorithmTestRunner:
    """Runs one bounded media test at a time outside the API event loop."""

    def __init__(self, analyzer_factory: Callable[[], VisionAnalyzer], store: JsonStateStore, output_dir: Path,
                 inference_fps: float = 0.5, settings_provider=None) -> None:
        self.settings_provider = settings_provider
        self.analyzer_factory = analyzer_factory
        self.inference_fps = inference_fps
        self._pending = 0
        self._inputs: dict[str, Path] = {}
        self._closed = False
        self.store = store
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="algorithm-test")
        self._lock = RLock()
        self._stop = StopEvent()
        self._conversion_lock = RLock()
        for record in store.list_algorithm_tests():
            if record.get("state") in {"queued", "running"}:
                record.update(state="failed", error="Server restarted before this test completed",
                              completed_at=datetime.now(timezone.utc).isoformat())
                store.put_algorithm_test(record)

    @staticmethod
    def _public(record: dict) -> dict:
        return {key: value for key, value in record.items() if key != "output_path"}

    def submit(self, filename: str, media_type: str, payload: bytes, camera: Camera | None = None) -> dict:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_IMAGES | SUPPORTED_VIDEOS:
            raise ValueError("supported files: JPG, PNG, WEBP, MP4, MOV, AVI, and MKV")
        job_id = str(uuid4())
        input_path = self.output_dir / f"{job_id}-input{suffix}"
        record = {
            "id": job_id,
            "filename": Path(filename).name,
            "media_type": media_type,
            "state": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "detections": [],
            "frames_processed": 0,
            "mode": "visual_analysis",
            "findings": [],
            "camera_id": camera.id if camera else None,
            "camera_name": camera.name if camera else None,
            "zones": [],
            "events": [],
            "inference_fps": self.inference_fps,
            "warnings": (["A still image cannot validate motion or duration-based behavior."] if suffix in SUPPORTED_IMAGES else [])
                        + ["Model descriptions require review. Tracking and automatic behavior alerts are disabled."],
        }
        with self._lock:
            if self._closed or self._pending >= 4:
                raise RuntimeError("Algorithm queue is full or shutting down; try again later")
            self._pending += 1
            try:
                input_path.write_bytes(payload)
                self.store.put_algorithm_test(record)
                self._inputs[job_id] = input_path
                self._executor.submit(self._run, record, input_path, suffix, camera)
            except Exception:
                self._pending -= 1
                self._inputs.pop(job_id, None)
                input_path.unlink(missing_ok=True)
                raise
            logger.info("test=%s queued type=%s bytes=%s mode=%s", job_id, suffix, len(payload), record["mode"])
            return self._public(record)

    def list(self) -> list[dict]:
        return [self._public(record) for record in self.store.list_algorithm_tests()]

    def get(self, job_id: str) -> dict:
        record = self._record(job_id)
        if record is None:
            raise KeyError(job_id)
        return self._public(record)

    def result(self, job_id: str) -> tuple[Path, str]:
        record = self._record(job_id)
        if record is None:
            raise KeyError(job_id)
        if record.get("state") != "completed" or not record.get("output_path"):
            raise RuntimeError("result is not ready")
        path = Path(record["output_path"])
        if path.parent.resolve() != self.output_dir.resolve() or not path.is_file():
            raise FileNotFoundError("result file is unavailable")
        if path.suffix == ".mp4":
            # Repair legacy MPEG-4 Part 2 results without deleting the original.
            with self._conversion_lock:
                converted = path.with_suffix(".webm")
                if not converted.exists():
                    self._convert_legacy(path, converted)
                record.update(output_path=str(converted.resolve()), output_media_type="video/webm")
                self.store.put_algorithm_test(record)
                return converted, "video/webm"
        return path, record["output_media_type"]

    def _convert_legacy(self, source: Path, target: Path) -> None:
        import cv2
        capture = cv2.VideoCapture(str(source))
        writer = None
        temporary = target.with_name(target.stem + "-converting.webm")
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
            if not capture.isOpened() or not 0 < fps <= 240:
                raise RuntimeError("Cannot read legacy result; please run the test again")
            size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            writer = WebMWriter(temporary, fps, size)
            count = 0
            while count < fps * 60:
                if self._stop.is_set():
                    raise RuntimeError("conversion cancelled")
                ok, frame = capture.read()
                if not ok:
                    break
                writer.write(frame)
                count += 1
            if not count:
                raise RuntimeError("Legacy result contains no readable frames")
            writer.release()
            temporary.replace(target)
            logger.info("legacy result converted to WebM")
        finally:
            capture.release()
            if writer is not None:
                writer.release()
            temporary.unlink(missing_ok=True)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._stop.set()
        for record in self.store.list_algorithm_tests():
            if record.get("state") == "queued":
                record.update(state="failed", error="Test cancelled during server shutdown",
                              completed_at=datetime.now(timezone.utc).isoformat())
                self.store.put_algorithm_test(record)
        self._executor.shutdown(wait=True, cancel_futures=True)
        with self._lock:
            for path in self._inputs.values():
                path.unlink(missing_ok=True)
            self._inputs.clear()
            self._pending = 0

    def _record(self, job_id: str) -> dict | None:
        return next((item for item in self.store.list_algorithm_tests() if item["id"] == job_id), None)

    def _save(self, record: dict, **changes) -> None:
        with self._lock:
            record.update(changes)
            self.store.put_algorithm_test(record)

    def _run(self, record: dict, input_path: Path, suffix: str, camera: Camera | None = None) -> None:
        logger.info("test=%s processing", record["id"])
        try:
            self._save(record, state="running", started_at=datetime.now(timezone.utc).isoformat())
            if self._stop.is_set():
                raise RuntimeError("test cancelled during server shutdown")
            analyzer = self.analyzer_factory()
            settings = self.settings_provider() if self.settings_provider else None
            session = VisionSession(analyzer, self._stop, settings=settings)
            if settings:
                self._save(record, inference_fps=settings.sample_fps, window_frames=settings.window_frames)
            if suffix in SUPPORTED_IMAGES:
                output_path, detections, frames = self._process_image(analyzer, input_path, record["id"], session)
                output_type = "image/jpeg"
            else:
                output_path, detections, frames = self._process_video(analyzer, input_path, record["id"], session)
                output_type = "video/webm"
            self._save(
                record,
                state="completed",
                detections=detections,
                frames_processed=frames,
                events=session.events,
                events_truncated=session.events_truncated,
                tracker=None,
                findings=session.findings,
                output_path=str(output_path.resolve()),
                output_media_type=output_type,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            logger.info("test=%s completed frames=%s", record["id"], frames)
        except Exception as error:
            logger.error("test=%s failed error_type=%s", record["id"], type(error).__name__)
            self._save(record, state="failed", error=str(error),
                       completed_at=datetime.now(timezone.utc).isoformat())
        finally:
            input_path.unlink(missing_ok=True)
            with self._lock:
                self._inputs.pop(record["id"], None)
                self._pending -= 1

    def _process_image(self, analyzer: VisionAnalyzer, input_path: Path, job_id: str,
                       session: VisionSession | None = None) -> tuple[Path, list[dict], int]:
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(input_path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("could not decode image")
        if frame.shape[0] * frame.shape[1] > 3840 * 2160:
            raise ValueError("image must have no more than 4K pixels")
        session = session or VisionSession(analyzer, self._stop)
        session.process(frame, 0, detect=True, activity=True)
        session.flush()
        session.draw(frame, 0)
        output_path = self.output_dir / f"{job_id}.jpg"
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise RuntimeError("could not encode result image")
        output_path.write_bytes(encoded.tobytes())
        return output_path, list(session.peak.values()), 1

    def _process_video(self, analyzer: VisionAnalyzer, input_path: Path, job_id: str,
                       session: VisionSession | None = None) -> tuple[Path, list[dict], int]:
        import cv2

        capture = cv2.VideoCapture(str(input_path))
        if not capture.isOpened():
            raise ValueError("could not decode video")
        fps = capture.get(cv2.CAP_PROP_FPS)
        fps = fps if 1 <= fps <= 120 else 24.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width < 1 or height < 1 or width * height > 3840 * 2160:
            capture.release()
            raise ValueError("video must have valid dimensions and no more than 4K pixels")
        output_path = self.output_dir / f"{job_id}.webm"
        try:
            writer = WebMWriter(output_path, fps, (width, height))
        except Exception:
            capture.release()
            raise
        session = session or VisionSession(analyzer, self._stop)
        next_detection = next_activity = 0.0
        max_frames = round(fps * 60)
        frame_count = 0
        try:
            while frame_count < max_frames:
                if self._stop.is_set():
                    raise RuntimeError("test cancelled during server shutdown")
                ok, frame = capture.read()
                if not ok:
                    break
                at = frame_count / fps
                detect, activity = at + 1e-9 >= next_detection, at + 1e-9 >= next_activity
                session.process(frame, at, detect, activity)
                if detect:
                    next_detection += 1 / self.inference_fps
                if activity:
                    next_activity += 0.5
                session.draw(frame, at)
                writer.write(frame)
                frame_count += 1
        finally:
            capture.release()
            writer.release()
        if frame_count == 0:
            output_path.unlink(missing_ok=True)
            raise ValueError("video contains no readable frames")
        session.flush()
        return output_path, list(session.peak.values()), frame_count

