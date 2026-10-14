"""Per-camera observation processing and configurable zone rules."""
from __future__ import annotations

from datetime import datetime, timezone
from math import dist, isfinite
from uuid import uuid4
from .domain import Camera, Detection, Event, Kind, Rule, Track, Zone
from .tracking import CentroidTracker, Tracker


class CameraAnalyzer:
    def __init__(self, camera: Camera, tracker: Tracker | None = None) -> None:
        self.camera = camera
        self.tracker = tracker if tracker is not None else CentroidTracker()
        self.previous_tracks: dict[int, Track] = {}
        self.crowd_entered: dict[str, float] = {}
        self.crowd_last_alert: dict[str, float] = {}
        self.last_at: float | None = None
        self.zone_activity_samples: dict[str, int] = {}
        self.zone_entered: dict[str, float] = {}
        self.zone_last_alert: dict[str, float] = {}
        self.zone_last_at: float | None = None

    def analyze(self, detections: list[Detection], at: float,
                zone_activity: dict[str, float] | None = None,
                process_zone_activity: bool = True) -> tuple[list[Track], list[Event]]:
        if not isfinite(at) or not 0 <= at <= 4102444800:
            raise ValueError("at must be a finite Unix timestamp through year 2100")
        if self.last_at is not None and at < self.last_at:
            raise ValueError("observations must arrive in timestamp order per camera")
        gap = self.last_at is not None and at - self.last_at > 2
        self.last_at = at
        tracks = self.tracker.update(detections, at)
        visible_ids = {track.id for track in tracks}
        for track in self.previous_tracks.values():
            if gap or track.id not in visible_ids:
                self._reset_dwell(track)
        if gap:
            self.crowd_entered.clear()
        self.previous_tracks = {track.id: track for track in tracks}
        events: list[Event] = []
        for track in tracks:
            for zone in self.camera.zones:
                if zone.rule == Rule.CROWD:
                    continue
                expected = (Kind.OBJECT if zone.rule == Rule.UNATTENDED_OBJECT else
                            Kind.VEHICLE if zone.rule == Rule.ILLEGAL_PARKING else Kind.PERSON)
                if track.kind != expected:
                    continue
                if zone.rule == Rule.DOOR_TAMPERING and zone_activity is not None:
                    continue
                inside = zone.contains(track.anchor)
                if not inside:
                    track.zone_entered.pop(zone.id, None)
                    track.zone_lowest_anchor.pop(zone.id, None)
                    track.upward_steps.pop(zone.id, None)
                    track.activity_samples.pop(zone.id, None)
                    track.crossed_lines.discard(zone.id)
                    track.stationary_anchor.pop(zone.id, None)
                    continue
                entered = track.zone_entered.setdefault(zone.id, at)
                if zone.rule in {Rule.ILLEGAL_PARKING, Rule.UNATTENDED_OBJECT}:
                    origin = track.stationary_anchor.setdefault(zone.id, track.anchor)
                    # Compare with the stationary origin, not the preceding frame:
                    # slow creeping must not accumulate a parked duration.
                    if dist(origin, track.anchor) > zone.stationary_tolerance:
                        track.stationary_anchor[zone.id] = track.anchor
                        track.zone_entered[zone.id] = entered = at
                    if zone.rule == Rule.UNATTENDED_OBJECT and any(
                            person.kind == Kind.PERSON and dist(person.anchor, track.anchor) <= zone.proximity_radius
                            for person in tracks):
                        # No ownership inference: any nearby visible person resets the timer.
                        track.zone_entered.pop(zone.id, None)
                        continue
                track.zone_lowest_anchor[zone.id] = max(track.zone_lowest_anchor.get(zone.id, track.anchor[1]), track.anchor[1])
                vertical_step = track.previous_anchor[1] - track.anchor[1]
                if vertical_step >= 0.01:
                    track.upward_steps[zone.id] = track.upward_steps.get(zone.id, 0) + 1
                elif vertical_step <= -0.01:
                    track.upward_steps[zone.id] = 0
                    track.crossed_lines.discard(zone.id)
                if (zone.crossing_line_y is not None and track.previous_anchor[1] > zone.crossing_line_y
                        >= track.anchor[1]):
                    track.crossed_lines.add(zone.id)
                if track.activity >= zone.activity_threshold:
                    track.activity_samples[zone.id] = track.activity_samples.get(zone.id, 0) + 1
                else:
                    track.activity_samples[zone.id] = 0
                if self._triggered(zone, track, at - entered):
                    last = track.last_alert.get(zone.id)
                    if last is None or at - last >= zone.cooldown_seconds:
                        track.last_alert[zone.id] = at
                        events.append(Event(str(uuid4()), self.camera.id, zone.id, track.id, track.kind, zone.rule,
                                            datetime.fromtimestamp(at, timezone.utc), track.confidence,
                                            f"Suspected {zone.rule.value.replace('_', ' ')} in {zone.id}"))
        events.extend(self._crowd_events(tracks, at))
        if zone_activity is not None and process_zone_activity:
            events.extend(self.analyze_zone_activity(zone_activity, at))
        return tracks, events

    @staticmethod
    def _reset_dwell(track: Track) -> None:
        track.zone_entered.clear()
        track.zone_lowest_anchor.clear()
        track.upward_steps.clear()
        track.activity_samples.clear()
        track.crossed_lines.clear()
        track.stationary_anchor.clear()

    def _crowd_events(self, tracks: list[Track], at: float) -> list[Event]:
        events = []
        for zone in self.camera.zones:
            if zone.rule != Rule.CROWD:
                continue
            people = [track for track in tracks if track.kind == Kind.PERSON and zone.contains(track.anchor)]
            if len(people) < zone.min_count:
                self.crowd_entered.pop(zone.id, None)
                continue
            entered = self.crowd_entered.setdefault(zone.id, at)
            if at - entered >= zone.dwell_seconds and at - self.crowd_last_alert.get(zone.id, float('-inf')) >= zone.cooldown_seconds:
                self.crowd_last_alert[zone.id] = at
                events.append(Event(str(uuid4()), self.camera.id, zone.id, None, Kind.PERSON, zone.rule,
                                    datetime.fromtimestamp(at, timezone.utc), min(track.confidence for track in people),
                                    f"Crowd threshold reached: {len(people)} people in {zone.id}; review required"))
        return events

    def analyze_zone_activity(self, zone_activity: dict[str, float], at: float) -> list[Event]:
        if not isfinite(at) or not 0 <= at <= 4102444800:
            raise ValueError("at must be a finite Unix timestamp through year 2100")
        if self.zone_last_at is not None and at < self.zone_last_at:
            raise ValueError("zone activity must arrive in timestamp order per camera")
        if self.zone_last_at is not None and at - self.zone_last_at > 2:
            self.zone_activity_samples.clear()
            self.zone_entered.clear()
        self.zone_last_at = at
        events: list[Event] = []
        for zone in self.camera.zones:
            if zone.rule != Rule.DOOR_TAMPERING:
                continue
            score = zone_activity.get(zone.id, 0.0)
            if not isfinite(score) or not 0 <= score <= 1:
                raise ValueError("zone activity must be between 0 and 1")
            if score < zone.activity_threshold:
                self.zone_activity_samples.pop(zone.id, None)
                self.zone_entered.pop(zone.id, None)
                continue
            entered = self.zone_entered.setdefault(zone.id, at)
            self.zone_activity_samples[zone.id] = self.zone_activity_samples.get(zone.id, 0) + 1
            if (at - entered >= zone.dwell_seconds
                    and self.zone_activity_samples[zone.id] >= zone.min_activity_samples
                    and at - self.zone_last_alert.get(zone.id, float("-inf")) >= zone.cooldown_seconds):
                self.zone_last_alert[zone.id] = at
                events.append(Event(str(uuid4()), self.camera.id, zone.id, None, None, zone.rule,
                                    datetime.fromtimestamp(at, timezone.utc), score,
                                    f"Suspected door-handle activity in {zone.id}"))
        return events

    @staticmethod
    def _triggered(zone: Zone, track: Track, dwell: float) -> bool:
        if zone.rule == Rule.INTRUSION:
            return True
        if zone.rule in {Rule.LOITERING, Rule.POOL_SAFETY, Rule.ILLEGAL_PARKING, Rule.UNATTENDED_OBJECT}:
            return dwell >= zone.dwell_seconds
        if zone.rule == Rule.WALL_CLIMBING:
            # Sustained ascent inside a calibrated wall zone is a review cue.
            return (dwell >= zone.dwell_seconds and track.upward_steps.get(zone.id, 0) >= 2
                    and track.zone_lowest_anchor[zone.id] - track.anchor[1] >= zone.min_vertical_travel
                    and (zone.crossing_line_y is None or zone.id in track.crossed_lines))
        if zone.rule == Rule.DOOR_TAMPERING:
            # Repeated local movement is a review cue, not evidence of damage.
            return dwell >= zone.dwell_seconds and track.activity_samples.get(zone.id, 0) >= zone.min_activity_samples
        return False
