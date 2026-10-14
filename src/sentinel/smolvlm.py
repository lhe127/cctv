"""Local Hugging Face adapter. No model/runtime types escape this module."""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from threading import Lock

from .vision import ModelBusy, SampledFrame, VisualFinding

MODEL_ID = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
MODEL_REVISION = "db3405a20a36b388e11e70afe17484666b8f3e1a"
PROMPT = (
    "Describe the people's observable actions and interactions in one or two short sentences. "
    "Focus on movement across the frames, not clothing or scenery. "
    "Look for punching, kicking, pushing, grappling, falling, or ordinary activities such as "
    "walking, talking, playing, and standing. Mention an action only if it is visibly supported; "
    "do not assume fighting because people are close together. "
    "If motion or contact is unclear, explicitly say uncertain and describe what is visible. "
    "Do not infer intent or identity."
)


class SmolVLM2Analyzer:
    """One lazy model per application, serialized inference, bounded input/output."""

    def __init__(self, model_path: str | None = None, device: str | None = None,
                 max_new_tokens: int = 96) -> None:
        self.model_path = model_path or os.getenv("SENTINEL_VLM_MODEL_PATH") or str(
            Path(__file__).resolve().parents[2] / "models" / "smolvlm2-500m")
        self.device = device or os.getenv("SENTINEL_VLM_DEVICE", "auto")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("SENTINEL_VLM_DEVICE must be auto, cpu, or cuda")
        if not 16 <= max_new_tokens <= 256:
            raise ValueError("max_new_tokens must be between 16 and 256")
        self.max_new_tokens = max_new_tokens
        self._lock = Lock()
        self._model = self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not Path(self.model_path, "config.json").is_file():
            raise RuntimeError("SmolVLM2 is not installed. Run python scripts/download_smolvlm.py.")
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as error:
            raise RuntimeError("Install the model runtime with python -m pip install -e '.[vlm]'.") from error
        device = ("cuda" if torch.cuda.is_available() else "cpu") if self.device == "auto" else self.device
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable; use SENTINEL_VLM_DEVICE=cpu.")
        # Local-only loading prevents surprise downloads during camera/API requests.
        processor = AutoProcessor.from_pretrained(self.model_path, local_files_only=True, trust_remote_code=False)
        model = AutoModelForImageTextToText.from_pretrained(
            self.model_path, local_files_only=True, trust_remote_code=False,
            dtype=torch.float16 if device == "cuda" else torch.float32,
            attn_implementation="sdpa",
        ).to(device).eval()
        self._processor, self._model = processor, model

    def analyze(self, frames: tuple[SampledFrame, ...]) -> VisualFinding:
        if not 1 <= len(frames) <= 8:
            raise ValueError("analysis requires between 1 and 8 sampled frames")
        if any(b.offset_seconds < a.offset_seconds for a, b in zip(frames, frames[1:])):
            raise ValueError("frames must be chronological")
        # Bound contention: a camera skips a busy window instead of creating a backlog.
        if not self._lock.acquire(timeout=1):
            raise ModelBusy("model is busy; waiting for the next analysis window")
        try:
            self._load()
            import torch
            from PIL import Image

            images = []
            for frame in frames:
                with Image.open(BytesIO(frame.jpeg)) as image:
                    image = image.convert("RGB")
                    image.thumbnail((512, 512))
                    images.append(image.copy())
            is_video = len(frames) > 1
            content = [{"type": "video" if is_video else "image"}, {"type": "text", "text": PROMPT}]
            text = self._processor.apply_chat_template(
                [{"role": "user", "content": content}], add_generation_prompt=True, tokenize=False)
            if is_video:
                import numpy as np
                from transformers.video_utils import VideoMetadata

                # Fixed-size letterboxing avoids distortion and bounds video tokens.
                video = []
                for image in images:
                    canvas = Image.new("RGB", (512, 512))
                    canvas.paste(image, ((512-image.width)//2, (512-image.height)//2))
                    video.append(np.asarray(canvas))
                indices = [round((frame.offset_seconds-frames[0].offset_seconds)*1000) for frame in frames]
                metadata = VideoMetadata(total_num_frames=indices[-1]+1, fps=1000,
                                         duration=indices[-1]/1000, frames_indices=indices)
                inputs = self._processor(text=text, videos=[[np.stack(video)]],
                    video_metadata=[metadata], do_sample_frames=False, do_resize=False, return_tensors="pt")
            else:
                inputs = self._processor(text=text, images=images, return_tensors="pt", do_resize=False)
            inputs = inputs.to(self._model.device)
            if "pixel_values" in inputs:
                inputs["pixel_values"] = inputs["pixel_values"].to(self._model.dtype)
            with torch.inference_mode():
                output = self._model.generate(**inputs, do_sample=False, max_new_tokens=self.max_new_tokens,
                                              no_repeat_ngram_size=4)
            description = self._processor.batch_decode(
                output[:, inputs["input_ids"].shape[-1]:], skip_special_tokens=True)[0].strip()
            if not description:
                raise RuntimeError("model returned an empty analysis")
            return VisualFinding(description, MODEL_ID, MODEL_REVISION, frames[0].offset_seconds,
                                 frames[-1].offset_seconds, len(frames))
        finally:
            self._lock.release()
