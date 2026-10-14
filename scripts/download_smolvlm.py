"""Download the pinned Apache-2.0 checkpoint; inference stays local afterwards."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sentinel.smolvlm import MODEL_ID, MODEL_REVISION


if __name__ == "__main__":
    from huggingface_hub import snapshot_download

    destination = Path(__file__).resolve().parents[1] / "models" / "smolvlm2-500m"
    snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_dir=destination,
                      allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja", "README.md", "LICENSE*"])
    print(f"SmolVLM2 installed at {destination}")
