"""Declared capabilities: availability is distinct from validation or accuracy."""

CAPABILITIES = [
    {"id": "A01", "name": "Live preview", "status": "implemented", "note": "Authenticated JPEG/MJPEG; no WebRTC."},
    {"id": "A02", "name": "Multi-camera monitoring", "status": "implemented", "note": "Independent workers; capacity depends on hardware."},
    {"id": "A03", "name": "Human detection and tracking", "status": "implemented", "note": "YOLOX ONNX + configurable ByteTrack; model file required."},
    {"id": "A04", "name": "Vehicle detection and tracking", "status": "implemented", "note": "COCO car, truck, bus and motorcycle grouped as vehicle."},
    {"id": "A05", "name": "Restricted-area entry", "rule": "intrusion", "status": "implemented", "note": "Person footpoint inside polygon."},
    {"id": "A06", "name": "Loitering", "rule": "loitering", "status": "implemented", "note": "Continuous observed track dwell in polygon."},
    {"id": "A07", "name": "Suspected climbing", "rule": "wall_climbing", "status": "heuristic", "note": "Bounding-box ascent; not pose/action classification."},
    {"id": "A08", "name": "Door-handle activity", "rule": "door_tampering", "status": "heuristic", "note": "Localized motion only; cannot establish intent."},
    {"id": "A09", "name": "Fighting", "status": "not_installed", "note": "Requires task-specific model and validation."},
    {"id": "A10", "name": "Human fall", "status": "not_installed", "note": "Requires pose/action model and validation."},
    {"id": "A11", "name": "Fire and smoke", "status": "not_installed", "note": "Requires licensed specialist weights and validation."},
    {"id": "A12", "name": "Drowning", "status": "not_installed", "note": "Requires specialist data and safety validation; not a lifeguard replacement."},
    {"id": "A13", "name": "Pool danger-zone presence", "rule": "pool_safety", "status": "implemented", "note": "Person entry/dwell only; does not detect drowning."},
    {"id": "A14", "name": "Unattended bag", "rule": "unattended_object", "status": "heuristic", "note": "Stationary backpack/handbag/suitcase without nearby people; no ownership inference."},
    {"id": "A15", "name": "Crowd threshold", "rule": "crowd", "status": "implemented", "note": "Sustained person count per zone, not calibrated density."},
    {"id": "A16", "name": "Suspected illegal parking", "rule": "illegal_parking", "status": "implemented", "note": "Stationary vehicle dwell in a configured no-parking zone."},
]
