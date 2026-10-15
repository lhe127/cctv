"""Local JSON adapters for camera configuration and durable activity history."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from .domain import Camera, Event, Kind, Rule, Zone, MapPosition


def _zone_from_dict(value: dict[str, Any]) -> Zone:
    default_meanings = {
        "intrusion": "restricted area",
        "loitering": "waiting area",
        "wall_climbing": "perimeter",
        "door_tampering": "main door",
        "pool_safety": "pool danger area",
        "crowd": "gathering area",
        "illegal_parking": "no parking",
    }
    return Zone(
        value["id"], Rule(value["rule"]), tuple(tuple(point) for point in value["polygon"]),
        value.get("dwell_seconds", 10), value.get("cooldown_seconds", 30),
        value.get("activity_threshold", 0.7), value.get("min_vertical_travel", 0.12),
        value.get("min_activity_samples", 2), value.get("crossing_line_y"),
        value.get("meaning", default_meanings.get(value["rule"], "custom")),
        value.get("min_count", 5), value.get("stationary_tolerance", 0.025), value.get("proximity_radius", 0.15),
    )


def _camera_from_dict(value: dict[str, Any]) -> Camera:
    source = value["source"]
    if isinstance(source, bool) or not isinstance(source, (str, int)) or (isinstance(source, int) and source < 0):
        raise ValueError("camera source must be a nonnegative webcam index or video source string")
    return Camera(value["id"], value["name"], source,
                  tuple(_zone_from_dict(zone) for zone in value.get("zones", [])),
                  MapPosition(**value["map_position"]) if value.get("map_position") else None)


def _camera_to_dict(camera: Camera) -> dict[str, Any]:
    return {
        "id": camera.id,
        "name": camera.name,
        "source": camera.source,
        "zones": [asdict(zone) for zone in camera.zones],
        "map_position": asdict(camera.map_position) if camera.map_position else None,
    }


class JsonCameraRepository:
    """Atomic local camera configuration storage."""

    def __init__(self, source_path: Path, write_path: Path | None = None) -> None:
        self.source_path = source_path
        self.write_path = write_path or source_path
        self._lock = RLock()

    def load(self) -> list[Camera]:
        if not self.source_path.exists():
            return []
        payload = json.loads(self.source_path.read_text(encoding="utf-8"))
        cameras = [_camera_from_dict(item) for item in payload.get("cameras", [])]
        if len({camera.id for camera in cameras}) != len(cameras):
            raise ValueError("camera ids must be unique")
        return cameras

    def save(self, cameras: list[Camera]) -> None:
        payload = {"cameras": [_camera_to_dict(camera) for camera in cameras]}
        with self._lock:
            self.write_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.write_path.with_suffix(self.write_path.suffix + ".tmp")
            try:
                temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                os.replace(temporary, self.write_path)
            except OSError:
                temporary.unlink(missing_ok=True)
                raise


class JsonStateStore:
    """Bounded, thread-safe persistence for alerts and algorithm-test jobs."""

    def __init__(self, path: Path, max_events: int = 1000, max_tests: int = 100) -> None:
        self.path = path
        self.max_events = max_events
        self.max_tests = max_tests
        self._lock = RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "events": [], "algorithm_tests": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Preserve the exact damaged bytes before starting a fresh history.
            # Permission/I/O errors and unsupported versions must still fail.
            backup = self.path.with_name(f"{self.path.name}.corrupt-{uuid4().hex}")
            self.path.rename(backup)
            logging.getLogger("sentinel.storage").warning(
                "Invalid state preserved at %s; starting empty history", backup
            )
            value = {"version": 1, "events": [], "algorithm_tests": [], "findings": []}
            self._write(value)
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError(f"unsupported state file: {self.path}")
        value.setdefault("events", [])
        value.setdefault("algorithm_tests", [])
        return value

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def load_events(self) -> list[Event]:
        with self._lock:
            result = []
            for item in self._read()["events"]:
                result.append(Event(
                    item["id"], item["camera_id"], item["zone_id"], item.get("track_id"),
                    Kind(item["kind"]) if item.get("kind") else None, Rule(item["rule"]),
                    datetime.fromisoformat(item["observed_at"]), item["confidence"], item["message"],
                ))
            return result

    def append_events(self, events: list[Event]) -> None:
        if not events:
            return
        with self._lock:
            value = self._read()
            value["events"].extend({
                "id": event.id,
                "camera_id": event.camera_id,
                "zone_id": event.zone_id,
                "track_id": event.track_id,
                "kind": event.kind.value if event.kind else None,
                "rule": event.rule.value,
                "observed_at": event.observed_at.isoformat(),
                "confidence": event.confidence,
                "message": event.message,
            } for event in events)
            value["events"] = value["events"][-self.max_events:]
            self._write(value)

    def list_algorithm_tests(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._read()["algorithm_tests"]))

    def load_findings(self) -> list[dict]:
        with self._lock:
            return self._read().get("findings", [])[-self.max_events:]

    def append_finding(self, finding: dict) -> None:
        with self._lock:
            value = self._read()
            value["findings"] = (value.get("findings", []) + [finding])[-self.max_events:]
            self._write(value)

    def put_algorithm_test(self, record: dict[str, Any]) -> None:
        with self._lock:
            value = self._read()
            tests = value["algorithm_tests"]
            for index, item in enumerate(tests):
                if item["id"] == record["id"]:
                    tests[index] = record
                    break
            else:
                tests.append(record)
            value["algorithm_tests"] = tests[-self.max_tests:]
            self._write(value)
