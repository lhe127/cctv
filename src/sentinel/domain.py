"""Framework-independent contracts for observations and safety events."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from typing import TypeAlias

Point: TypeAlias = tuple[float, float]
Box: TypeAlias = tuple[float, float, float, float]


class Kind(StrEnum):
    PERSON = "person"
    VEHICLE = "vehicle"
    OBJECT = "object"  # COCO backpack, handbag and suitcase only


class Rule(StrEnum):
    INTRUSION = "intrusion"
    LOITERING = "loitering"
    WALL_CLIMBING = "wall_climbing"
    DOOR_TAMPERING = "door_tampering"
    POOL_SAFETY = "pool_safety"
    CROWD = "crowd"
    ILLEGAL_PARKING = "illegal_parking"
    UNATTENDED_OBJECT = "unattended_object"


@dataclass(frozen=True)
class Detection:
    kind: Kind
    box: Box  # normalized x1,y1,x2,y2
    confidence: float
    activity: float = 0.0  # optional, externally estimated manipulation/motion score

    def __post_init__(self) -> None:
        x1, y1, x2, y2 = self.box
        if not all(isfinite(v) and 0 <= v <= 1 for v in self.box) or x1 >= x2 or y1 >= y2:
            raise ValueError("box must be ordered normalized coordinates")
        if not 0 <= self.confidence <= 1 or not 0 <= self.activity <= 1:
            raise ValueError("confidence and activity must be between 0 and 1")

    @property
    def anchor(self) -> Point:
        x1, _, x2, y2 = self.box
        return ((x1 + x2) / 2, y2)


@dataclass(frozen=True)
class Zone:
    id: str
    rule: Rule
    polygon: tuple[Point, ...]
    dwell_seconds: float = 10.0
    cooldown_seconds: float = 30.0
    activity_threshold: float = 0.7
    min_vertical_travel: float = 0.12
    min_activity_samples: int = 2
    crossing_line_y: float | None = None
    meaning: str = "custom"
    min_count: int = 5
    stationary_tolerance: float = 0.025
    proximity_radius: float = 0.15

    def __post_init__(self) -> None:
        if not self.id or len(self.polygon) < 3:
            raise ValueError("zone needs an id and at least three points")
        if any(not isfinite(x) or not isfinite(y) or not 0 <= x <= 1 or not 0 <= y <= 1 for x, y in self.polygon):
            raise ValueError("zone points must be normalized")
        if (not isfinite(self.dwell_seconds) or not isfinite(self.cooldown_seconds)
                or self.dwell_seconds < 0 or self.cooldown_seconds < 0 or not 0 <= self.activity_threshold <= 1
                or not 0 < self.min_vertical_travel <= 1 or self.min_activity_samples < 1):
            raise ValueError("invalid rule threshold")
        if isinstance(self.min_count, bool) or not isinstance(self.min_count, int) or not 2 <= self.min_count <= 1000:
            raise ValueError("min_count must be an integer between 2 and 1000")
        if not isfinite(self.stationary_tolerance) or not 0 < self.stationary_tolerance <= 0.25:
            raise ValueError("stationary_tolerance must be between 0 (exclusive) and 0.25")
        if not isfinite(self.proximity_radius) or not 0 < self.proximity_radius <= 1:
            raise ValueError("proximity_radius must be between 0 (exclusive) and 1")
        if self.crossing_line_y is not None and (not isfinite(self.crossing_line_y) or not 0 < self.crossing_line_y < 1):
            raise ValueError("crossing_line_y must be between 0 and 1")
        if (self.crossing_line_y is not None and self.rule == Rule.WALL_CLIMBING
                and not min(y for _, y in self.polygon) < self.crossing_line_y < max(y for _, y in self.polygon)):
            raise ValueError("crossing_line_y must pass through the wall zone")
        if not self.meaning.strip() or len(self.meaning) > 80:
            raise ValueError("zone meaning must be between 1 and 80 characters")

    def contains(self, point: Point) -> bool:
        x, y = point
        inside = False
        previous = self.polygon[-1]
        for current in self.polygon:
            x1, y1 = previous
            x2, y2 = current
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
            previous = current
        return inside


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    source: str | int  # synthetic, webcam index, local video path, or RTSP URL
    zones: tuple[Zone, ...] = ()


@dataclass
class Track:
    id: int
    kind: Kind
    box: Box
    confidence: float
    first_seen: float
    last_seen: float
    previous_anchor: Point
    anchor: Point
    activity: float = 0.0
    zone_entered: dict[str, float] = field(default_factory=dict)
    last_alert: dict[str, float] = field(default_factory=dict)
    zone_lowest_anchor: dict[str, float] = field(default_factory=dict)
    upward_steps: dict[str, int] = field(default_factory=dict)
    activity_samples: dict[str, int] = field(default_factory=dict)
    crossed_lines: set[str] = field(default_factory=set)
    stationary_anchor: dict[str, Point] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    id: str
    camera_id: str
    zone_id: str
    track_id: int | None
    kind: Kind | None
    rule: Rule
    observed_at: datetime
    confidence: float
    message: str


@dataclass(frozen=True)
class DetectionRecord:
    camera_id: str
    track_id: int
    kind: Kind
    confidence: float
    observed_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
