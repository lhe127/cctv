"""Optional OpenCV video and ONNX detector adapters."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event as StopEvent, RLock, Thread
from time import monotonic, time
from typing import Callable, Protocol

from .domain import Camera, Detection, Kind, Rule, Zone
from .service import MonitorService
from .vendor.opencv_zoo_yolox import YoloX


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


class OpenCvZooYoloXDetector:
    """Adapter for the pinned Apache-2.0 OpenCV Zoo YOLOX-S COCO model."""

    def __init__(self, model_path: str, threshold: float = 0.45) -> None:
        import cv2
        self.cv2 = cv2
        self.net = YoloX(model_path, confThreshold=threshold, objThreshold=threshold)

    def detect(self, frame: object) -> list[Detection]:
        import numpy as np
        cv2 = self.cv2
        height, width = frame.shape[:2]
        ratio = min(640 / width, 640 / height)
        resized = cv2.resize(frame, (round(width * ratio), round(height * ratio)))
        padded = np.full((640, 640, 3), 114, dtype=np.float32)
        padded[:resized.shape[0], :resized.shape[1]] = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        predictions = self.net.infer(padded)
        result: list[Detection] = []
        for x, y, box_width, box_height, confidence, class_id in predictions:
            class_id = int(class_id)
            if class_id not in (0, 2, 3, 5, 7):
                continue
            x1, y1 = max(0.0, float(x) / ratio / width), max(0.0, float(y) / ratio / height)
            x2, y2 = min(1.0, float(x + box_width) / ratio / width), min(1.0, float(y + box_height) / ratio / height)
            if x1 < x2 and y1 < y2:
                result.append(Detection(Kind.PERSON if class_id == 0 else Kind.VEHICLE,
                                        (x1, y1, x2, y2), float(confidence)))
        return result


class YoloOnnxDetector:
    """Adapter for a user supplied COCO YOLOv8-style ONNX model; no weights bundled."""

    def __init__(self, model_path: str, threshold: float = 0.4) -> None:
        import cv2
        self.cv2 = cv2
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.threshold = threshold

    def detect(self, frame: object) -> list[Detection]:
        import numpy as np
        cv2 = self.cv2
        size = 640
        resized = cv2.resize(frame, (size, size))
        blob = cv2.dnn.blobFromImage(resized, scalefactor=1 / 255.0, size=(size, size), swapRB=True)
        self.net.setInput(blob)
        output = self.net.forward()
        rows = np.squeeze(output)
        if rows.ndim != 2:
            raise ValueError("expected YOLOv8 output matrix")
        if rows.shape[0] == 84:  # 4 coordinates + 80 COCO classes
            rows = rows.T
        if rows.shape[1] != 84:
            raise ValueError("expected COCO YOLOv8 output with 84 columns")
        boxes: list[list[int]] = []
        scores: list[float] = []
        kinds: list[Kind] = []
        for row in rows:
            cls = int(np.argmax(row[4:]))
            score = float(row[4 + cls])
            if score < self.threshold or cls not in (0, 2, 3, 5, 7):
                continue
            cx, cy, bw, bh = [float(v) for v in row[:4]]
            boxes.append([int(cx - bw / 2), int(cy - bh / 2), int(bw), int(bh)])
            scores.append(score)
            kinds.append(Kind.PERSON if cls == 0 else Kind.VEHICLE)
        result: list[Detection] = []
        for index in cv2.dnn.NMSBoxes(boxes, scores, self.threshold, 0.45):
            x, y, w, h = boxes[int(index)]
            x1, y1 = max(0, x / size), max(0, y / size)
            x2, y2 = min(1, (x + w) / size), min(1, (y + h) / size)
            if x1 < x2 and y1 < y2:
                result.append(Detection(kinds[int(index)], (x1, y1, x2, y2), scores[int(index)]))
        return result


class CaptureWorker:
    def __init__(self, camera: Camera, service: MonitorService, detector: Detector, on_error: Callable[[str], None]) -> None:
        self.camera, self.service, self.detector, self.on_error = camera, service, detector, on_error
        self.stop_event = StopEvent()
        self._frame_ready = StopEvent()
        self._frame_lock = RLock()
        self._latest_frame: object | None = None
        self.activity_estimator = FrameActivityEstimator()
        self.capture_thread = Thread(target=self._capture, name=f"capture-{camera.id}", daemon=True)
        self.detect_thread = Thread(target=self._detect, name=f"detect-{camera.id}", daemon=True)

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
            reached_end = False
            try:
                next_preview = 0.0
                next_activity = 0.0
                fps = capture.get(cv2.CAP_PROP_FPS) if file_source else 0.0
                playback_start = monotonic()
                frame_index = 0
                while not self.stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        reached_end = True
                        break
                    if file_source and 0 < fps <= 240:
                        if self.stop_event.wait(max(0.0, playback_start + frame_index / fps - monotonic())):
                            break
                    frame_index += 1
                    with self._frame_lock:
                        self._latest_frame = frame
                        self._frame_ready.set()
                    now = monotonic()
                    if now >= next_activity:
                        camera = next(item for item in self.service.cameras() if item.id == self.camera.id)
                        if any(zone.rule == Rule.DOOR_TAMPERING for zone in camera.zones):
                            _, scores = self.activity_estimator.measure(frame, [], camera.zones)
                            self.service.observe_zone_activity(self.camera.id, scores, time())
                        next_activity = now + 0.5  # Door motion does not wait for slow person inference.
                    if now >= next_preview:
                        encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if encoded:
                            self.service.set_frame(self.camera.id, jpeg.tobytes())
                            self.service.set_status(self.camera.id, "running", type(self.detector).__name__)
                        next_preview = now + 0.1  # Limit JPEG work to ten previews per second.
            except Exception as error:
                self.on_error(f"camera {self.camera.id}: {error}")
            finally:
                capture.release()
            if file_source and reached_end and not self.stop_event.is_set():
                self.service.set_status(self.camera.id, "finished", type(self.detector).__name__)
                self.stop_event.set()
                self._frame_ready.set()
                break
            self.stop_event.wait(1)

    def _detect(self) -> None:
        while not self.stop_event.is_set():
            if not self._frame_ready.wait(0.2):
                continue
            with self._frame_lock:
                frame = self._latest_frame
                self._frame_ready.clear()
            if frame is None or self.stop_event.is_set():
                continue
            try:
                detections = self.detector.detect(frame)
                if not self.stop_event.is_set():
                    self.service.observe(self.camera.id, detections, time(), {}, process_zone_activity=False)
            except Exception as error:
                self.on_error(f"camera {self.camera.id}: detection failed: {error}")
                self.stop_event.set()
                return


class CaptureController:
    """Starts each video source only when requested and releases it on stop."""

    def __init__(self, service: MonitorService, detector_factory: Callable[[], Detector]) -> None:
        self.service = service
        self.detector_factory = detector_factory
        self._lock = RLock()
        self._workers: dict[str, CaptureWorker] = {}

    def start(self, camera_id: str) -> dict[str, object]:
        with self._lock:
            camera = next((item for item in self.service.cameras() if item.id == camera_id), None)
            if camera is None:
                raise KeyError(camera_id)
            if camera.source == "synthetic":
                raise ValueError("synthetic camera has no video source")
            if camera_id in self._workers:
                if self._workers[camera_id].is_alive():
                    return self.service.status(camera_id)
                self._workers.pop(camera_id).stop()
                self.service.clear_live(camera_id)
            detector = self.detector_factory()
            self.service.set_status(camera_id, "starting", type(detector).__name__)
            worker = CaptureWorker(camera, self.service, detector,
                lambda error: self.service.set_status(camera_id, "error", type(detector).__name__, error))
            self._workers[camera_id] = worker
            worker.start()
            return self.service.status(camera_id)

    def stop(self, camera_id: str) -> dict[str, object]:
        with self._lock:
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
