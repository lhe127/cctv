"""Capabilities exposed by the active local visual-analysis pipeline."""

CAPABILITIES = [
    {"id": "A01", "name": "Live preview", "status": "implemented", "note": "Authenticated JPEG/MJPEG."},
    {"id": "A02", "name": "Multi-camera sampling", "status": "implemented", "note": "One shared model; busy windows can be skipped."},
    {"id": "V01", "name": "Image and video descriptions", "status": "experimental", "note": "Local SmolVLM2 sampled-frame analysis; human review required."},
]
