"""Qwen Cloud adapter: bounded HTTPS requests, no redirects, no silent fallback."""
import base64
import http.client
import json
from threading import Lock

from .settings import effective_key
from .vision import ModelBusy, VisualFinding
from .vision_response import ALERT_FORMAT, parse_danger_response


class QwenAnalyzer:
    def __init__(self, connection_factory=http.client.HTTPSConnection):
        self.connection_factory = connection_factory
        self._lock = Lock()

    def analyze(self, frames, *, settings):
        if not 1 <= len(frames) <= 8:
            raise ValueError("analysis requires between 1 and 8 sampled frames")
        if any(b.offset_seconds < a.offset_seconds for a, b in zip(frames, frames[1:])):
            raise ValueError("frames must be chronological")
        key = effective_key(settings)
        if not key or not settings.qwen_workspace:
            raise RuntimeError("Qwen API key or workspace ID is missing. Update Settings.")
        if not self._lock.acquire(timeout=1):
            raise ModelBusy("cloud model is busy; waiting for the next analysis window")
        connection = None
        try:
            content = [{"type": "text", "text": settings.prompt + ALERT_FORMAT +
                        "\nThe following images are chronological sampled video frames. "
                        "Evaluate the entire sequence, including brief hazards in any frame."}]
            for frame in frames:
                content.extend([
                    {"type": "text", "text": f"Frame at {frame.offset_seconds:.3f} seconds:"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," +
                     base64.b64encode(frame.jpeg).decode("ascii")}},
                ])
            body = json.dumps({"model": settings.qwen_model, "messages": [{"role": "user", "content": content}],
                               "max_tokens": settings.max_new_tokens, "stream": False,
                               "enable_thinking": False})
            host = f"{settings.qwen_workspace}.{settings.qwen_region}.maas.aliyuncs.com"
            connection = self.connection_factory(host, timeout=settings.qwen_timeout)
            connection.request("POST", "/compatible-mode/v1/chat/completions", body=body.encode("utf-8"),
                               headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                # Never expose provider bodies: they can echo requests/credentials.
                raise RuntimeError(f"Qwen request failed (HTTP {response.status}). Check key, region, workspace, model and quota.")
            raw = response.read(262145)
            if len(raw) > 262144:
                raise RuntimeError("Qwen response exceeded the size limit.")
            try:
                data = json.loads(raw)
                choice = data["choices"][0]
                text = choice["message"]["content"]
                if not isinstance(text, str):
                    raise ValueError()
            except (ValueError, KeyError, IndexError, TypeError):
                raise RuntimeError("Qwen returned an invalid response.") from None
            # Defensive redaction even if a provider unexpectedly echoes its key.
            decision, evidence, warning = parse_danger_response(text.replace(key, "[redacted]"))
            if choice.get("finish_reason") != "stop":
                decision, warning = "uncertain", "Incomplete Qwen response. Review source or increase output tokens."
            return VisualFinding(evidence or "No usable model response.", settings.qwen_model, "cloud-unpinned",
                                 frames[0].offset_seconds, frames[-1].offset_seconds, len(frames),
                                 danger_status=decision, analysis_warning=warning)
        except (OSError, http.client.HTTPException):
            raise RuntimeError("Qwen connection failed or timed out. Check connectivity and Settings.") from None
        finally:
            if connection is not None:
                connection.close()
            self._lock.release()


class ConfiguredAnalyzer:
    """Both live and recorded pipelines share this provider selector."""
    def __init__(self, settings_provider, local, cloud=None):
        self.settings_provider = settings_provider
        self.local = local
        self.cloud = cloud or QwenAnalyzer()

    def analyze(self, frames):
        settings = self.settings_provider()
        provider = self.cloud if settings.qwen_enabled else self.local
        return provider.analyze(frames, settings=settings)
