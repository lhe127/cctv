"""OpenCV capture and bounded local visual analysis."""
from __future__ import annotations

from dataclasses import replace
import os
import logging
from pathlib import Path
from threading import Event as StopEvent, RLock, Thread
from time import monotonic, time
from typing import Callable, Protocol

from .domain import Camera, Detection, Kind, Rule, Zone
from .service import MonitorService
from collections import deque
from .vision import ANALYSIS_WINDOW_FRAMES, SAMPLE_INTERVAL_SECONDS, ModelBusy, VisionAnalyzer, sample_frame

logger = logging.getLogger("sentinel.video")


class Detector(Protocol):
    def detect(self, frame: object) -> list[Detection]: ...


class FrameActivityEstimator:
    """Estimate person and small door-zone motion from consecutive frames."""

    def __init__(self) -> None:
        self.previous_gray: object | None = None

    def annotate(self, frame: object, detections: list[Detection]) -> list[Detection]:
        annotated, _ = self.measure(frame, detections, ())
        return annotated

    def measure(self, frame: object, detections: list[Detection],
                zones: tuple[Zone, ...]) -> tuple[list[Detection], dict[str, float]]:
        import cv2
        import numpy as np

        door_zones = tuple(zone for zone in zones if zone.rule == Rule.DOOR_TAMPERING)
        scores = {zone.id: 0.0 for zone in door_zones}
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        previous = self.previous_gray
        self.previous_gray = gray
        if previous is None or previous.shape != gray.shape:
            return detections, scores
        changed = cv2.absdiff(previous, gray) >= 25
        # A lighting change or camera shake across most of the frame is not local interaction.
        if np.count_nonzero(changed) / changed.size > 0.35:
            return [replace(item, activity=0.0) if item.kind == Kind.PERSON else item for item in detections], scores
        height, width = gray.shape
        for zone in door_zones:
            polygon = np.array([(round(x * (width - 1)), round(y * (height - 1)))
                                for x, y in zone.polygon], dtype=np.int32)
            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [polygon], 1)
            area = int(np.count_nonzero(mask))
            # A handle zone must be small enough to separate interaction from door movement.
            if area < 16 or area > changed.size * 0.12:
                continue
            local_fraction = float(np.count_nonzero(changed & (mask != 0))) / area
            x, y, w, h = cv2.boundingRect(polygon)
            x1, y1 = max(0, x - w), max(0, y - h)
            x2, y2 = min(width, x + 2 * w), min(height, y + 2 * h)
            context = changed[y1:y2, x1:x2]
            outside = mask[y1:y2, x1:x2] == 0
            context_fraction = float(np.count_nonzero(context & outside)) / max(1, np.count_nonzero(outside))
            # Hand tools and flashlights also move nearby pixels. Require the lock
            # area to change more than its surroundings, rather than a still ring.
            concentrated_motion = local_fraction - 1.5 * context_fraction
            if concentrated_motion > 0:
                scores[zone.id] = float(min(1.0, concentrated_motion / 0.05))
        annotated: list[Detection] = []
        for detection in detections:
            if detection.kind != Kind.PERSON:
                annotated.append(detection)
                continue
            x1, y1, x2, y2 = detection.box
            patch = changed[int(y1 * height):max(int(y1 * height) + 1, int(y2 * height)),
                            int(x1 * width):max(int(x1 * width) + 1, int(x2 * width))]
            motion_fraction = float(np.count_nonzero(patch)) / patch.size if patch.size else 0.0
            annotated.append(replace(detection, activity=min(1.0, motion_fraction / 0.05)))
        return annotated, scores


class EmptyDetector:
    def detect(self, frame: object) -> list[Detection]:
        return []


class CaptureWorker:
    """Independent preview and bounded VLM sampling; no object/zone inference."""
    def __init__(self, camera: Camera, service: MonitorService, analyzer: VisionAnalyzer, on_error: Callable[[str], None], settings=None) -> None:
        self.camera, self.service, self.analyzer, self.on_error = camera, service, analyzer, on_error
        self.preview_fps = max(1, min(15, float(os.getenv("SENTINEL_PREVIEW_FPS", "5"))))
        self.sample_interval = 1 / settings.sample_fps if settings else SAMPLE_INTERVAL_SECONDS
        self.window_frames = settings.window_frames if settings else ANALYSIS_WINDOW_FRAMES
        if settings:
            self.preview_fps = settings.preview_fps
        self.stop_event = StopEvent()
        self._ended = StopEvent()
        self._frame_ready = StopEvent()
        self._frame_lock = RLock()
        self._samples = deque(maxlen=self.window_frames)
        self.capture_thread = Thread(target=self._capture, name=f"capture-{camera.id}", daemon=True)
        self.detect_thread = Thread(target=self._detect, name=f"analysis-{camera.id}", daemon=True)

    def start(self) -> None:
        self.detect_thread.start()
        self.capture_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._frame_ready.set()
        self.capture_thread.join(timeout=5)
        self.detect_thread.join(timeout=5)

    def is_alive(self) -> bool:
        return self.capture_thread.is_alive() or self.detect_thread.is_alive()

    def _capture(self) -> None:
        import cv2
        file_source = isinstance(self.camera.source, str) and Path(self.camera.source).is_file()
        while not self.stop_event.is_set():
            capture = cv2.VideoCapture(self.camera.source)
            if not capture.isOpened():
                self.on_error(f"camera {self.camera.id}: cannot open source")
                capture.release()
                self.stop_event.wait(2)
                continue
            try:
                next_preview = next_sample = 0.0
                fps = capture.get(cv2.CAP_PROP_FPS) if file_source else 0.0
                fps = fps if 0 < fps <= 240 else 24.0
                started = monotonic()
                frame_index = 0
                while not self.stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if file_source and self.stop_event.wait(max(0.0, started + frame_index / fps - monotonic())):
                        break
                    at = frame_index / fps if file_source else monotonic() - started
                    frame_index += 1
                    now = monotonic()
                    if at >= next_sample:
                        with self._frame_lock:
                            self._samples.append(sample_frame(frame, at))
                            if len(self._samples) >= self.window_frames:
                                self._frame_ready.set()
                        next_sample = at + self.sample_interval
                    if now >= next_preview:
                        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if ok:
                            self.service.set_frame(self.camera.id, jpeg.tobytes())
                            self.service.set_status(self.camera.id, "running", "visual-analysis")
                        next_preview = now + 1 / self.preview_fps
                if file_source:
                    self._ended.set()
                    self._frame_ready.set()
                    return
                if self.stop_event.is_set():
                    return
                with self._frame_lock:
                    self._samples.clear()  # Never combine frames across a disconnection.
                self.on_error(f"camera {self.camera.id}: source disconnected")
            except Exception:
                self.on_error(f"camera {self.camera.id}: capture failed")
            finally:
                capture.release()
            self.stop_event.wait(1)

    def _detect(self) -> None:
        while not self.stop_event.is_set():
            if not self._frame_ready.wait(0.2):
                continue
            if self.stop_event.is_set():
                return
            with self._frame_lock:
                frames = tuple(self._samples)
                self._samples.clear()
                self._frame_ready.clear()
            if frames:
                try:
                    self.service.set_analysis_status(self.camera.id, "analyzing")
                    finding = self.analyzer.analyze(frames)
                    if not self.stop_event.is_set():
                        self.service.record_finding(self.camera.id, finding)
                except ModelBusy:
                    self.service.set_analysis_status(self.camera.id, "waiting")
                    if self._ended.is_set():
                        with self._frame_lock:
                            self._samples.extend(frames)
                            self._frame_ready.set()
                        self.stop_event.wait(0.5)
                        continue
                except Exception as error:
                    self.service.set_analysis_status(self.camera.id, "error", str(error))
                    self.stop_event.set()
                    self.on_error(f"camera {self.camera.id}: analysis failed; see analysis status")
                    return
            if self._ended.is_set():
                with self._frame_lock:
                    if self._samples:
                        self._frame_ready.set()
                        continue
                self.service.set_status(self.camera.id, "finished", "visual-analysis")
                return


class CaptureController:
    """Starts each video source only when requested and releases it on stop."""

    def __init__(self, service: MonitorService, analyzer_factory: Callable[[], VisionAnalyzer], settings_provider=None) -> None:
        self.settings_provider = settings_provider
        self.service = service
        self.analyzer_factory = analyzer_factory
        self._lock = RLock()
        self._workers: dict[str, CaptureWorker] = {}

    def start(self, camera_id: str) -> dict[str, object]:
        with self._lock:
            camera = next((item for item in self.service.cameras() if item.id == camera_id), None)
            if camera is None:
                raise KeyError(camera_id)
            if camera.source == "synthetic":
                raise ValueError("synthetic camera has no video source")
            logger.info("camera=%s start requested", camera_id)
            if camera_id in self._workers:
                if self._workers[camera_id].is_alive():
                    return self.service.status(camera_id)
                self._workers.pop(camera_id).stop()
                self.service.clear_live(camera_id)
            analyzer = self.analyzer_factory()
            self.service.set_status(camera_id, "starting", "visual-analysis")
            worker = CaptureWorker(camera, self.service, analyzer,
                lambda error: self.service.set_status(camera_id, "error", "visual-analysis", error),
                settings=self.settings_provider() if self.settings_provider else None)
            self._workers[camera_id] = worker
            worker.start()
            return self.service.status(camera_id)

    def stop(self, camera_id: str) -> dict[str, object]:
        with self._lock:
            logger.info("camera=%s stop requested", camera_id)
            self.service.status(camera_id)  # validates id
            worker = self._workers.pop(camera_id, None)
            if worker:
                worker.stop()
                if worker.is_alive():
                    self._workers[camera_id] = worker
                    raise RuntimeError("camera worker did not stop")
            self.service.clear_live(camera_id)
            self.service.set_status(camera_id, "stopped")
            return self.service.status(camera_id)

    def stop_all(self) -> None:
        for camera_id in list(self._workers):
            self.stop(camera_id)
