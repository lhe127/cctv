"""Application API and in-memory, bounded monitoring state."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from .analysis import CameraAnalyzer
from .domain import Camera, Detection, DetectionRecord, Event, Track, Zone


class MonitorService:
    def __init__(self, max_events: int = 1000) -> None:
        self._lock = RLock()
        self._cameras: dict[str, Camera] = {}
        self._analyzers: dict[str, CameraAnalyzer] = {}
        self._tracks: dict[str, list[Track]] = {}
        self._seen_track_ids: dict[str, set[int]] = {}
        self._events: deque[Event] = deque(maxlen=max_events)
        self._detections: deque[DetectionRecord] = deque(maxlen=max_events)
        self._frames: dict[str, bytes] = {}
        self._states: dict[str, dict[str, object]] = {}

    def add_camera(self, camera: Camera) -> None:
        with self._lock:
            if camera.id in self._cameras:
                raise ValueError(f"duplicate camera id: {camera.id}")
            self._cameras[camera.id] = camera
            self._analyzers[camera.id] = CameraAnalyzer(camera)
            self._tracks[camera.id] = []
            self._seen_track_ids[camera.id] = set()
            self._states[camera.id] = {"state": "stopped", "detector": None, "error": None,
                                       "last_frame_at": None, "last_observation_at": None}

    def cameras(self) -> list[Camera]:
        with self._lock:
            return list(self._cameras.values())

    def set_zones(self, camera_id: str, zones: tuple[Zone, ...]) -> None:
        with self._lock:
            camera = self._cameras.get(camera_id)
            if camera is None:
                raise KeyError(camera_id)
            if len({zone.id for zone in zones}) != len(zones):
                raise ValueError("zone ids must be unique per camera")
            updated = replace(camera, zones=zones)
            self._cameras[camera_id] = updated
            self._analyzers[camera_id] = CameraAnalyzer(updated)
            self._tracks[camera_id] = []
            self._seen_track_ids[camera_id].clear()
            self._states[camera_id]["last_observation_at"] = None

    def observe(self, camera_id: str, detections: list[Detection], at: float,
                zone_activity: dict[str, float] | None = None,
                process_zone_activity: bool = True) -> tuple[list[Track], list[Event]]:
        with self._lock:
            analyzer = self._analyzers.get(camera_id)
            if analyzer is None:
                raise KeyError(camera_id)
            tracks, events = analyzer.analyze(detections, at, zone_activity, process_zone_activity)
            self._detections.extend(DetectionRecord(camera_id, track.id, track.kind, track.confidence,
                datetime.fromtimestamp(at, timezone.utc)) for track in tracks if track.id not in self._seen_track_ids[camera_id])
            self._seen_track_ids[camera_id].update(track.id for track in tracks)
            self._tracks[camera_id] = tracks
            self._events.extend(events)
            self._states[camera_id]["last_observation_at"] = datetime.fromtimestamp(at, timezone.utc)
            return tracks, events

    def observe_zone_activity(self, camera_id: str, scores: dict[str, float], at: float) -> list[Event]:
        with self._lock:
            analyzer = self._analyzers.get(camera_id)
            if analyzer is None:
                raise KeyError(camera_id)
            events = analyzer.analyze_zone_activity(scores, at)
            self._events.extend(events)
            if scores:
                self._states[camera_id]["last_observation_at"] = datetime.fromtimestamp(at, timezone.utc)
            return events

    def tracks(self, camera_id: str) -> list[Track]:
        with self._lock:
            if camera_id not in self._cameras:
                raise KeyError(camera_id)
            return list(self._tracks[camera_id])

    def events(self, camera_id: str | None = None) -> list[Event]:
        with self._lock:
            return [event for event in reversed(self._events) if camera_id is None or event.camera_id == camera_id]

    def detections(self, camera_id: str | None = None) -> list[DetectionRecord]:
        with self._lock:
            return [item for item in reversed(self._detections) if camera_id is None or item.camera_id == camera_id]

    def status(self, camera_id: str) -> dict[str, object]:
        with self._lock:
            if camera_id not in self._cameras:
                raise KeyError(camera_id)
            return dict(self._states[camera_id])

    def set_status(self, camera_id: str, state: str, detector: str | None = None, error: str | None = None) -> None:
        with self._lock:
            if camera_id not in self._cameras:
                raise KeyError(camera_id)
            status = self._states[camera_id]
            status.update(state=state, detector=detector, error=error)

    def clear_live(self, camera_id: str) -> None:
        with self._lock:
            if camera_id not in self._cameras:
                raise KeyError(camera_id)
            self._frames.pop(camera_id, None)
            self._tracks[camera_id] = []
            self._seen_track_ids[camera_id].clear()
            self._analyzers[camera_id] = CameraAnalyzer(self._cameras[camera_id])
            self._states[camera_id]["last_frame_at"] = None
            self._states[camera_id]["last_observation_at"] = None

    def set_frame(self, camera_id: str, jpeg: bytes) -> None:
        with self._lock:
            if camera_id not in self._cameras:
                raise KeyError(camera_id)
            self._frames[camera_id] = jpeg
            self._states[camera_id]["last_frame_at"] = datetime.now(timezone.utc)

    def frame(self, camera_id: str) -> bytes | None:
        with self._lock:
            if camera_id not in self._cameras:
                raise KeyError(camera_id)
            return self._frames.get(camera_id)
