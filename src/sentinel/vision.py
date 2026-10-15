"""Model-independent contracts for bounded visual analysis."""
from __future__ import annotations

# Shared bounded action window for recorded and live media (3.5 seconds at 2 FPS).
SAMPLE_INTERVAL_SECONDS = 0.5
ANALYSIS_WINDOW_FRAMES = 8

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Protocol


@dataclass(frozen=True)
class SampledFrame:
    jpeg: bytes
    offset_seconds: float

    def __post_init__(self) -> None:
        if not self.jpeg or not isfinite(self.offset_seconds) or self.offset_seconds < 0:
            raise ValueError("a sampled frame requires image bytes and a nonnegative timestamp")


@dataclass(frozen=True)
class VisualFinding:
    description: str
    model: str
    revision: str
    start_seconds: float
    end_seconds: float
    frames_analyzed: int
    review_required: bool = True
    danger_status: str = "uncertain"
    analysis_warning: str | None = None

    def __post_init__(self) -> None:
        if self.danger_status not in {"yes", "no", "uncertain"}:
            raise ValueError("danger_status must be yes, no, or uncertain")

    def public(self) -> dict:
        return asdict(self)


class VisionAnalyzer(Protocol):
    """Replace this adapter to adopt another VLM without changing callers."""

    def analyze(self, frames: tuple[SampledFrame, ...]) -> VisualFinding: ...


class ModelBusy(RuntimeError):
    """An analyzer has no available capacity; callers may retry or drop live work."""


def sample_frame(frame: object, at: float, max_edge: int = 512) -> SampledFrame:
    """Bound memory before handing OpenCV frames across the application boundary."""
    import cv2

    height, width = frame.shape[:2]
    scale = min(1.0, max_edge / max(height, width))
    if scale < 1:
        frame = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ValueError("could not encode analysis frame")
    return SampledFrame(encoded.tobytes(), at)
