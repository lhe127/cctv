"""Small dependency-free tracker; state is isolated per camera."""
from __future__ import annotations

from math import dist
from .domain import Detection, Track


class CentroidTracker:
    def __init__(self, max_distance: float = 0.18, max_age: float = 2.0) -> None:
        self.max_distance = max_distance
        self.max_age = max_age
        self._next_id = 1
        self._tracks: dict[int, Track] = {}

    def update(self, detections: list[Detection], at: float) -> list[Track]:
        self._tracks = {key: value for key, value in self._tracks.items() if at - value.last_seen <= self.max_age}
        candidates = sorted(
            (dist(track.anchor, detection.anchor), track.id, index)
            for track in self._tracks.values()
            for index, detection in enumerate(detections)
            if track.kind == detection.kind and dist(track.anchor, detection.anchor) <= self.max_distance
        )
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        for _, track_id, index in candidates:
            if track_id in matched_tracks or index in matched_detections:
                continue
            track, detection = self._tracks[track_id], detections[index]
            track.previous_anchor = track.anchor
            track.anchor = detection.anchor
            track.box = detection.box
            track.confidence = detection.confidence
            track.activity = detection.activity
            track.last_seen = at
            matched_tracks.add(track_id)
            matched_detections.add(index)
        for index, detection in enumerate(detections):
            if index in matched_detections:
                continue
            identifier = self._next_id
            self._next_id += 1
            self._tracks[identifier] = Track(identifier, detection.kind, detection.box, detection.confidence, at, at, detection.anchor, detection.anchor, detection.activity)
            matched_tracks.add(identifier)
        return [self._tracks[key] for key in sorted(matched_tracks)]
