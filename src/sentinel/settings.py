"""Validated local analysis configuration with atomic, thread-safe persistence."""
import os
import json
from typing import Literal
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .prompts import SURVEILLANCE_PROMPT as PROMPT


class AnalysisSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(default=PROMPT, min_length=1, max_length=4000)
    sample_fps: float = Field(default=2, ge=0.25, le=10, allow_inf_nan=False)
    window_frames: int = Field(default=8, ge=1, le=8, strict=True)
    max_new_tokens: int = Field(default=96, ge=16, le=256, strict=True)
    preview_fps: float = Field(default=5, ge=1, le=15, allow_inf_nan=False)
    qwen_enabled: bool = False
    qwen_model: str = Field(default="qwen3-vl-plus", pattern=r"^qwen[a-zA-Z0-9_.-]{1,100}$")
    qwen_region: Literal["ap-southeast-1", "cn-beijing", "us-east-1", "eu-central-1"] = "ap-southeast-1"
    qwen_workspace: str = Field(default="", pattern=r"^[a-zA-Z0-9-]{0,80}$")
    qwen_timeout: int = Field(default=45, ge=5, le=90, strict=True)
    qwen_api_key: SecretStr = Field(default=SecretStr(""), exclude=True)


class SettingsUpdate(AnalysisSettings):
    clear_qwen_api_key: bool = False


class SettingsOutput(AnalysisSettings):
    qwen_key_configured: bool = False


def effective_key(value: AnalysisSettings) -> str:
    return value.qwen_api_key.get_secret_value() or os.getenv("DASHSCOPE_API_KEY", "").strip()


def public_settings(value: AnalysisSettings) -> SettingsOutput:
    return SettingsOutput(**value.model_dump(), qwen_key_configured=bool(effective_key(value)))


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
                data = value.model_dump()
                data["qwen_api_key"] = value.qwen_api_key.get_secret_value()
                temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                os.replace(temporary, self.path)
                self._value = value
            finally:
                temporary.unlink(missing_ok=True)

    def update(self, value: SettingsUpdate) -> AnalysisSettings:
        with self._lock:
            key = (SecretStr("") if value.clear_qwen_api_key else
                   value.qwen_api_key if value.qwen_api_key.get_secret_value() else self._value.qwen_api_key)
            merged = AnalysisSettings(**value.model_dump(exclude={"clear_qwen_api_key"}), qwen_api_key=key)
            if merged.qwen_enabled and (not effective_key(merged) or not merged.qwen_workspace):
                raise ValueError("Qwen requires an API key and workspace ID before enabling cloud analysis.")
            if any(ord(char) < 33 or ord(char) > 126 for char in effective_key(merged)):
                raise ValueError("API key must contain printable characters without spaces.")
            self.save(merged)
            return merged
