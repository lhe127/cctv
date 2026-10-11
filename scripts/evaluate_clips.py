"""Small, repeatable regression check for the owner's local demonstration clips."""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from sentinel.analysis import CameraAnalyzer
from sentinel.domain import Camera, Rule, Zone
from sentinel.video import FrameActivityEstimator, OpenCvZooYoloXDetector


def evaluate(path: Path, zone: Zone, interval: float, stop_at: float | None,
             detector: OpenCvZooYoloXDetector) -> list[float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open {path}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    end = min(duration, stop_at) if stop_at is not None else duration
    analyzer = CameraAnalyzer(Camera(path.stem, path.stem, str(path), (zone,)))
    activity = FrameActivityEstimator()
    alerts: list[float] = []
    try:
        t = 0.0
        while t < end:
            capture.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"cannot decode {path} at {t:.1f}s")
            detections, scores = activity.measure(frame, detector.detect(frame), (zone,))
            _, events = analyzer.analyze(detections, t, scores)
            alerts.extend([t] * len(events))
            t += interval
    finally:
        capture.release()
    return alerts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", type=Path, default=Path("media/test-clips"))
    args = parser.parse_args()
    detector = OpenCvZooYoloXDetector("models/object_detection_yolox_2022nov.onnx")

    climbing = Zone("climb", Rule.WALL_CLIMBING,
                    ((0.001, 0.001), (0.999, 0.001), (0.999, 0.999), (0.001, 0.999)),
                    dwell_seconds=2, crossing_line_y=0.7)
    climb_alerts = evaluate(args.media_dir / "climbing-video.mp4", climbing, 1.0, 34.0, detector)
    climb_windows = ((8, 14), (26, 32))  # Manually checked climbing moments, approximate seconds.
    detected_windows = sum(any(start <= alert <= end for alert in climb_alerts)
                           for start, end in climb_windows)
    print(f"A07: {detected_windows}/{len(climb_windows)} labeled climbing windows alerted; "
          f"alert seconds: {climb_alerts}")

    handle = Zone("handle", Rule.DOOR_TAMPERING,
                  ((0.33, 0.39), (0.45, 0.39), (0.45, 0.56), (0.33, 0.56)),
                  dwell_seconds=0.4, activity_threshold=0.5, min_activity_samples=2)
    door_alerts = evaluate(args.media_dir / "open-door-video.mp4", handle, 0.5, None, detector)
    print(f"A08: {len(door_alerts)} alerts on labeled ordinary door opening; "
          f"alert seconds: {door_alerts}")

    lock = Zone("lock", Rule.DOOR_TAMPERING,
                ((0.50, 0.37), (0.61, 0.37), (0.61, 0.53), (0.50, 0.53)),
                dwell_seconds=0.4, activity_threshold=0.5, min_activity_samples=2)
    tamper_alerts = evaluate(args.media_dir / "door-tampering-video.mp4", lock, 0.5, None, detector)
    print(f"A08: {len(tamper_alerts)} alerts on staged lock-tool footage; "
          f"alert seconds: {tamper_alerts}")
    return 0 if (detected_windows == len(climb_windows) and not door_alerts
                 and any(6 <= alert <= 9 for alert in tamper_alerts)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
