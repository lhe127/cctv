import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np
import pytest

from sentinel.algorithm_test import AlgorithmTestRunner
from sentinel.domain import Camera, Detection, Kind, Rule, Zone
from sentinel.vision_session import VisionSession
from sentinel.vision import VisualFinding
from threading import Event
from sentinel.storage import JsonStateStore


@pytest.fixture(autouse=True)
def no_webm_codec_tag_warning(capfd):
    yield
    assert "'VP80' is not supported" not in capfd.readouterr().err


class FakeDetector:
    def analyze(self, frames):
        return VisualFinding("A person is visible.", "fixture", "test", frames[0].offset_seconds,
                             frames[-1].offset_seconds, len(frames))


class AlgorithmTestRunnerTests(unittest.TestCase):
    def test_recorded_analysis_uses_media_time_without_legacy_alerts(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            root = Path(directory)
            source = root / "scene.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 4, (100, 80))
            for _ in range(12):
                writer.write(np.zeros((80, 100, 3), dtype=np.uint8))
            writer.release()
            store = JsonStateStore(root / "state.json")
            runner = AlgorithmTestRunner(FakeDetector, store, root / "results")
            camera = Camera("saved", "Saved camera", "rtsp://private:secret@device",
                            (Zone("pool", Rule.POOL_SAFETY, ((0, 0), (1, 0), (1, 1), (0, 1)), dwell_seconds=1),))
            try:
                job = runner.submit("scene.avi", "video/avi", source.read_bytes(), camera)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and runner.get(job["id"])["state"] not in {"completed", "failed"}:
                    time.sleep(.02)
                result = runner.get(job["id"])
                self.assertEqual(result["state"], "completed", result)
                self.assertEqual(result["events"], [])
                self.assertEqual(result["findings"][0]["start_seconds"], 0)
                self.assertEqual(result["findings"][0]["end_seconds"], 2.5)
                self.assertEqual(result["findings"][0]["frames_analyzed"], 6)
                self.assertNotIn("secret", str(result))
                self.assertEqual(store.load_events(), [])
                self.assertEqual(store.list_algorithm_tests()[0]["zones"], [])
            finally:
                runner.close()

    def test_queue_is_bounded_and_shutdown_removes_pending_inputs(self):
        gate = Event()
        class BlockingDetector:
            def analyze(self, frames):
                gate.wait(3)
                return FakeDetector().analyze(frames)
        with tempfile.TemporaryDirectory(dir=".") as directory:
            root = Path(directory)
            runner = AlgorithmTestRunner(BlockingDetector, JsonStateStore(root / "state.json"), root / "results")
            _, image = cv2.imencode('.jpg', np.zeros((80, 100, 3), dtype=np.uint8))
            try:
                for _ in range(4):
                    runner.submit("test.jpg", "image/jpeg", image.tobytes())
                with self.assertRaises(RuntimeError):
                    runner.submit("test.jpg", "image/jpeg", image.tobytes())
            finally:
                gate.set()
                runner.close()
            self.assertEqual(list((root / "results").glob('*-input*')), [])

    def test_still_image_cannot_accumulate_dwell(self):
        camera = Camera("saved", "Saved", "synthetic", (Zone("wait", Rule.LOITERING,
                        ((0, 0), (1, 0), (1, 1), (0, 1)), dwell_seconds=1),))
        session = VisionSession(FakeDetector())
        session.process(np.zeros((80, 100, 3), dtype=np.uint8), 0, True, True)
        session.flush()
        self.assertEqual(session.events, [])
        self.assertEqual(session.findings[0]["frames_analyzed"], 1)

    def test_video_output_and_legacy_conversion_are_webm(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            root = Path(directory)
            store = JsonStateStore(root / "state.json")
            runner = AlgorithmTestRunner(FakeDetector, store, root / "results")
            source = root / "scene.mp4"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 5, (100, 80))
            self.assertTrue(writer.isOpened())
            for index in range(10):
                writer.write(np.full((80, 100, 3), index * 20, dtype=np.uint8))
            writer.release()
            try:
                path, _, count = runner._process_video(FakeDetector(), source, "test")
                self.assertEqual(path.suffix, ".webm")
                self.assertEqual(path.read_bytes()[:4], bytes.fromhex("1a45dfa3"))
                self.assertEqual(count, 10)
                legacy = root / "results" / "legacy.mp4"
                legacy.write_bytes(source.read_bytes())
                store.put_algorithm_test({"id": "legacy", "state": "completed",
                                          "output_path": str(legacy.resolve()), "output_media_type": "video/mp4"})
                converted, media_type = runner.result("legacy")
                self.assertEqual(media_type, "video/webm")
                self.assertTrue(legacy.exists())
                self.assertTrue(converted.exists())
                self.assertEqual(runner.result("legacy"), (converted, media_type))
                for preview in (path, converted):
                    decoded = cv2.VideoCapture(str(preview))
                    try:
                        decoded_count = 0
                        while True:
                            ok, frame = decoded.read()
                            if not ok:
                                break
                            self.assertEqual(frame.shape, (80, 100, 3))
                            decoded_count += 1
                        self.assertEqual(decoded_count, 10)
                        self.assertAlmostEqual(decoded.get(cv2.CAP_PROP_FPS), 5, places=2)
                    finally:
                        decoded.release()
            finally:
                runner.close()

    def test_image_finding_and_preview_are_persisted(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            root = Path(directory)
            store = JsonStateStore(root / "state.json")
            runner = AlgorithmTestRunner(FakeDetector, store, root / "results")
            ok, encoded = cv2.imencode(".jpg", np.zeros((80, 100, 3), dtype=np.uint8))
            self.assertTrue(ok)
            job = runner.submit("scene.jpg", "image/jpeg", encoded.tobytes())
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and runner.get(job["id"])["state"] not in {"completed", "failed"}:
                time.sleep(0.02)
            result = runner.get(job["id"])
            self.assertEqual(result["state"], "completed", result)
            self.assertEqual(result["detections"], [])
            self.assertEqual(result["findings"][0]["description"], "A person is visible.")
            path, media_type = runner.result(job["id"])
            self.assertTrue(path.is_file())
            self.assertEqual(media_type, "image/jpeg")
            self.assertEqual(JsonStateStore(root / "state.json").list_algorithm_tests()[0]["id"], job["id"])
            runner.close()
