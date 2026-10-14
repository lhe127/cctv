"""Print SmolVLM2 descriptions for the first 60 seconds of a local video."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sentinel.smolvlm import SmolVLM2Analyzer
from sentinel.vision_session import VisionSession


def main():
    import cv2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    args = parser.parse_args()
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise RuntimeError("could not open video")
    fps = capture.get(cv2.CAP_PROP_FPS)
    fps = fps if 1 <= fps <= 120 else 24
    session = VisionSession(SmolVLM2Analyzer())
    try:
        for index in range(round(fps * 60)):
            ok, frame = capture.read()
            if not ok:
                break
            session.process(frame, index / fps)
        session.flush()
    finally:
        capture.release()
    print(json.dumps(session.findings, indent=2))


if __name__ == "__main__":
    main()
