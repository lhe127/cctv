"""Human-review alert application service; no model text is executed as code."""
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Protocol

from .domain import Camera, MapPosition


class AlertStore(Protocol):
    def create_alert(self, alert: dict) -> dict: ...
    def list_alerts(self) -> list[dict]: ...
    def set_alert_status(self, alert_id: str, status: str, at: str) -> dict: ...


class AlertService:
    def __init__(self, store: AlertStore):
        self.store = store

    def record_finding(self, finding: dict, camera: Camera | None = None) -> dict | None:
        """Idempotent application function invoked for a model's explicit danger result."""
        if finding.get("danger_status") != "yes":
            return None
        now = finding.get("observed_at") or datetime.now(timezone.utc).isoformat()
        position = camera.map_position if camera else None
        if finding.get("job_id") and finding.get("map_position") is not None:
            position = MapPosition(**finding["map_position"])
        return self.store.create_alert({
            "id": finding["id"], "finding_id": finding["id"],
            "camera_id": camera.id if camera else finding.get("camera_id"),
            "camera_name": camera.name if camera else None,
            "map_position": asdict(position) if position else None,
            "source": "media_job" if finding.get("job_id") else "camera",
            "job_id": finding.get("job_id"), "description": finding["description"],
            "model": finding["model"], "revision": finding["revision"],
            "start_seconds": finding["start_seconds"], "end_seconds": finding["end_seconds"],
            "frames_analyzed": finding["frames_analyzed"], "review_required": True,
            "status": "pending", "created_at": now, "updated_at": now, "resolved_at": None,
        })

    def list(self, status: str | None = None) -> list[dict]:
        return [item for item in self.store.list_alerts() if status is None or item["status"] == status]

    def set_status(self, alert_id: str, status: str) -> dict:
        if status not in {"pending", "resolved"}:
            raise ValueError("status must be pending or resolved")
        return self.store.set_alert_status(alert_id, status, datetime.now(timezone.utc).isoformat())
