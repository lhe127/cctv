"""Validated local analysis configuration with atomic, thread-safe persistence."""
import os
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from .smolvlm import PROMPT


class AnalysisSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(default=PROMPT, min_length=1, max_length=4000)
    sample_fps: float = Field(default=2, ge=0.25, le=10, allow_inf_nan=False)
    window_frames: int = Field(default=8, ge=1, le=8, strict=True)
    max_new_tokens: int = Field(default=96, ge=16, le=256, strict=True)
    preview_fps: float = Field(default=5, ge=1, le=15, allow_inf_nan=False)


class JsonSettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
        self._value = (AnalysisSettings.model_validate_json(path.read_text(encoding="utf-8"))
                       if path.exists() else AnalysisSettings(preview_fps=float(os.getenv("SENTINEL_PREVIEW_FPS", "5"))))

    def get(self) -> AnalysisSettings:
        with self._lock:
            return self._value

    def save(self, value: AnalysisSettings) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            try:
                temporary.write_text(value.model_dump_json(indent=2) + "\n", encoding="utf-8")
                os.replace(temporary, self.path)
                self._value = value
            finally:
                temporary.unlink(missing_ok=True)
