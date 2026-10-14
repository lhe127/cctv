"""Supervision ByteTrack adapter; vendor objects never enter the rule engine."""
from __future__ import annotations

from .domain import Detection, Kind, Track


class ByteTrackAdapter:
    def __init__(self, frame_rate: float = 2, max_age: float = 2) -> None:
        import supervision as sv
        self._sv = sv
        self._engines = {kind: sv.ByteTrack(track_activation_threshold=0.35,
                         lost_track_buffer=round(30 * max_age), frame_rate=max(1, round(frame_rate)))
                         for kind in Kind}
        self._tracks: dict[tuple[Kind, int], Track] = {}
        self._next_id = 1
        self._last_at: float | None = None
        self.max_age = max_age

    def update(self, detections: list[Detection], at: float) -> list[Track]:
        import numpy as np
        if self._last_at is not None and at - self._last_at > self.max_age:
            for engine in self._engines.values():
                engine.reset()
            self._tracks.clear()
        self._last_at = at
        self._tracks = {key: track for key, track in self._tracks.items() if at - track.last_seen <= self.max_age}
        result = []
        # Separate association pools prevent a person and vehicle sharing an ID.
        for kind, engine in self._engines.items():
            indices = [i for i, detection in enumerate(detections) if detection.kind == kind]
            batch = self._sv.Detections(
                xyxy=np.array([detections[i].box for i in indices], dtype=float).reshape(-1, 4) * 1000,
                confidence=np.array([detections[i].confidence for i in indices], dtype=float),
                class_id=np.zeros(len(indices), dtype=int),
                data={"source_index": np.array(indices, dtype=int)},
            )
            tracked = engine.update_with_detections(batch)
            if not len(tracked):
                continue
            for source_index, vendor_id in zip(tracked.data["source_index"], tracked.tracker_id):
                detection = detections[int(source_index)]
                key = (kind, int(vendor_id))
                track = self._tracks.get(key)
                if track is None:
                    track = Track(self._next_id, kind, detection.box, detection.confidence,
                                  at, at, detection.anchor, detection.anchor, detection.activity)
                    self._next_id += 1
                    self._tracks[key] = track
                else:
                    track.previous_anchor, track.anchor = track.anchor, detection.anchor
                    track.box, track.confidence = detection.box, detection.confidence
                    track.last_seen, track.activity = at, detection.activity
                result.append(track)
        return sorted(result, key=lambda track: track.id)
