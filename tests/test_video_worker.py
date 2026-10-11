"""The video preview must keep updating while slow inference runs."""
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from sentinel.domain import Camera, Detection, Kind, Rule, Zone
from sentinel.service import MonitorService
from sentinel.video import CaptureWorker, FrameActivityEstimator


class FakeCapture:
    def __init__(self, source):
        self.reads = 0
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        time.sleep(0.02)
        self.reads += 1
        return True, np.full((4, 4, 3), self.reads % 255, dtype=np.uint8)

    def release(self):
        self.released = True


class SlowDetector:
    def __init__(self):
        self.frames = []

    def detect(self, frame):
        time.sleep(0.18)
        self.frames.append(frame)
        return []


class FiniteCapture(FakeCapture):
    def read(self):
        self.reads += 1
        if self.reads > 4:
            return False, None
        return True, np.zeros((4, 4, 3), dtype=np.uint8)

    def get(self, property_id):
        return 10.0


class DoorMotionCapture(FakeCapture):
    def read(self):
        time.sleep(0.05)
        self.reads += 1
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        if self.reads % 20 >= 10:
            frame[44:47, 44:54] = 255
        return True, frame


class VerySlowDetector:
    def detect(self, frame):
        time.sleep(1.5)
        return []


class CaptureWorkerTests(unittest.TestCase):
    def test_webcam_motion_can_trigger_door_review_alert(self):
        zone = Zone("door", Rule.DOOR_TAMPERING,
                    ((0.1, 0.1), (0.6, 0.1), (0.6, 0.9), (0.1, 0.9)), dwell_seconds=1)
        service = MonitorService()
        service.add_camera(Camera("webcam", "Webcam", 0, (zone,)))
        estimator = FrameActivityEstimator()
        person = Detection(Kind.PERSON, (0.2, 0.2, 0.4, 0.7), 0.9)
        still = np.zeros((100, 100, 3), dtype=np.uint8)
        changed = still.copy()
        changed[30:45, 25:35] = 255
        changed_again = changed.copy()
        changed_again[30:45, 25:35] = 0
        first = estimator.annotate(still, [person])
        self.assertEqual(first[0].activity, 0)
        self.assertEqual(service.observe("webcam", first, 100)[1], [])
        second = estimator.annotate(changed, [person])
        self.assertGreaterEqual(second[0].activity, zone.activity_threshold)
        self.assertEqual(service.observe("webcam", second, 101)[1], [])
        third = estimator.annotate(changed_again, [person])
        self.assertEqual(service.observe("webcam", third, 102)[1][0].rule, Rule.DOOR_TAMPERING)
        self.assertEqual(estimator.annotate(changed_again, [person])[0].activity, 0)

    def test_global_brightness_change_is_not_door_activity(self):
        estimator = FrameActivityEstimator()
        person = Detection(Kind.PERSON, (0.2, 0.2, 0.4, 0.7), 0.9)
        estimator.annotate(np.zeros((100, 100, 3), dtype=np.uint8), [person])
        bright = np.full((100, 100, 3), 255, dtype=np.uint8)
        self.assertEqual(estimator.annotate(bright, [person])[0].activity, 0)

    def test_small_handle_motion_without_person_and_context_suppression(self):
        zone = Zone("handle", Rule.DOOR_TAMPERING,
                    ((0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)), dwell_seconds=1)
        estimator = FrameActivityEstimator()
        service = MonitorService()
        service.add_camera(Camera("door", "Door", 0, (zone,)))
        still = np.zeros((100, 100, 3), dtype=np.uint8)
        _, first_scores = estimator.measure(still, [], (zone,))
        service.observe("door", [], 100, first_scores)
        handle = still.copy()
        handle[44:47, 44:54] = 255
        _, scores = estimator.measure(handle, [], (zone,))
        self.assertGreaterEqual(scores["handle"], zone.activity_threshold)
        self.assertEqual(service.observe("door", [], 101, scores)[1], [])
        _, scores = estimator.measure(still, [], (zone,))
        self.assertEqual(service.observe("door", [], 102, scores)[1][0].rule, Rule.DOOR_TAMPERING)
        estimator.measure(handle, [], (zone,))
        wider_change = handle.copy()
        wider_change[25:75, 25:75] = 255
        _, scores = estimator.measure(wider_change, [], (zone,))
        self.assertLess(scores["handle"], zone.activity_threshold)

    def test_video_file_is_paced_and_finishes(self):
        service = MonitorService()
        service.add_camera(Camera("clip", "Clip", "clip.mp4"))
        capture = FiniteCapture("clip.mp4")
        worker = CaptureWorker(service.cameras()[0], service, SlowDetector(), lambda error: None)
        with patch.object(Path, "is_file", return_value=True), patch.object(
            cv2, "VideoCapture", return_value=capture
        ), patch.object(cv2, "imencode", return_value=(True, np.array([1], dtype=np.uint8))):
            started = time.monotonic()
            worker.start()
            worker.capture_thread.join(timeout=2)
            elapsed = time.monotonic() - started
            worker.stop()
        self.assertFalse(worker.is_alive())
        self.assertTrue(capture.released)
        self.assertEqual(capture.reads, 5)
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertEqual(service.status("clip")["state"], "finished")

    def test_door_motion_does_not_wait_for_person_inference(self):
        zone = Zone("handle", Rule.DOOR_TAMPERING,
                    ((0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)),
                    dwell_seconds=0.5, min_activity_samples=2)
        service = MonitorService()
        service.add_camera(Camera("door", "Door", 0, (zone,)))
        worker = CaptureWorker(service.cameras()[0], service, VerySlowDetector(), lambda error: None)
        with patch.object(cv2, "VideoCapture", return_value=DoorMotionCapture(0)), patch.object(
            cv2, "imencode", return_value=(True, np.array([1], dtype=np.uint8))
        ):
            worker.start()
            try:
                time.sleep(1.3)
                self.assertTrue(any(event.rule == Rule.DOOR_TAMPERING for event in service.events("door")))
            finally:
                worker.stop()

    def test_preview_advances_while_detection_is_slow(self):
        service = MonitorService()
        service.add_camera(Camera("webcam", "Webcam", 0))
        capture = FakeCapture(0)
        detector = SlowDetector()
        errors = []
        worker = CaptureWorker(service.cameras()[0], service, detector, errors.append)
        with patch.object(cv2, "VideoCapture", return_value=capture), patch.object(
            cv2, "imencode", side_effect=lambda extension, frame, options: (True, np.array([frame[0, 0, 0]], dtype=np.uint8))
        ):
            worker.start()
            try:
                time.sleep(0.4)
                preview_frame = service.frame("webcam")
                self.assertIsNotNone(preview_frame)
                self.assertGreater(preview_frame[0], len(detector.frames) * 2)
                self.assertEqual(service.status("webcam")["state"], "running")
            finally:
                worker.stop()
        self.assertFalse(worker.is_alive())
        self.assertTrue(capture.released)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
