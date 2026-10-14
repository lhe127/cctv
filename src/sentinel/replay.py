"""Isolated recorded-media session using the live camera analysis contracts."""
from __future__ import annotations

from dataclasses import asdict

from .analysis import CameraAnalyzer
from .domain import Camera, Event, Rule, Track
from .tracking import Tracker
from .video import Detector, FrameActivityEstimator


class ReplaySession:
    def __init__(self, camera: Camera, detector: Detector, tracker: Tracker) -> None:
        self.camera = camera
        self.detector = detector
        self.analyzer = CameraAnalyzer(camera, tracker)
        self.motion = FrameActivityEstimator()
        self.tracks: list[Track] = []
        self.events: list[dict] = []
        self.events_truncated = False
        self.peak: dict[str, dict] = {}

    def process(self, frame, at: float, detect: bool, activity: bool) -> None:
        if detect:
            detections = self.detector.detect(frame)
            self.tracks, events = self.analyzer.analyze(detections, at, {}, process_zone_activity=False)
            self._record(events)
            for track in self.tracks:
                item = {"kind": track.kind.value, "confidence": round(track.confidence, 4), "box": list(track.box)}
                if track.kind.value not in self.peak or self.peak[track.kind.value]["confidence"] < track.confidence:
                    self.peak[track.kind.value] = item
        if activity and any(zone.rule == Rule.DOOR_TAMPERING for zone in self.camera.zones):
            _, scores = self.motion.measure(frame, [], self.camera.zones)
            self._record(self.analyzer.analyze_zone_activity(scores, at))

    def _record(self, events: list[Event]) -> None:
        for event in events:
            if len(self.events) >= 1000:
                self.events_truncated = True
                break
            item = asdict(event)
            item.pop("observed_at")
            item["offset_seconds"] = round(event.observed_at.timestamp(), 3)
            self.events.append(item)

    def draw(self, frame, at: float) -> None:
        import cv2
        import numpy as np
        height, width = frame.shape[:2]
        active = {event["zone_id"] for event in self.events if 0 <= at - event["offset_seconds"] <= 3}
        for zone in self.camera.zones:
            polygon = np.array([(round(x * (width - 1)), round(y * (height - 1))) for x, y in zone.polygon], dtype=np.int32)
            color = (40, 120, 255) if zone.id in active else (220, 180, 70)
            cv2.polylines(frame, [polygon], True, color, 2)
            cv2.putText(frame, zone.id[:40], tuple(polygon[0]), cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1)
        for track in self.tracks:
            x1, y1, x2, y2 = track.box
            cv2.rectangle(frame, (round(x1*width), round(y1*height)), (round(x2*width), round(y2*height)), (93, 220, 164), 2)
            cv2.putText(frame, f"{track.kind.value} #{track.id} {track.confidence:.0%}",
                        (round(x1*width), max(18, round(y1*height)-7)), cv2.FONT_HERSHEY_SIMPLEX, .5, (93, 220, 164), 1)
        latest = [event for event in self.events if 0 <= at - event["offset_seconds"] <= 3]
        if latest:
            label = " | ".join(dict.fromkeys(event["rule"] for event in latest))
            cv2.putText(frame, label[:100], (10, max(20, height-15)), cv2.FONT_HERSHEY_SIMPLEX, .55, (40, 120, 255), 2)
