import asyncio
from pathlib import Path
from threading import Event
import time

import cv2
import httpx
import numpy as np
import pytest

from sentinel.api import create_app
from sentinel.domain import Camera
from sentinel.smolvlm import SmolVLM2Analyzer
from sentinel.vision import ModelBusy, SampledFrame, VisualFinding, sample_frame
from sentinel.vision_session import VisionSession
from sentinel.video import CaptureWorker
from sentinel.service import MonitorService


class FixtureAnalyzer:
    def __init__(self):
        self.windows = []

    def analyze(self, frames):
        self.windows.append(frames)
        return VisualFinding("Fixture scene <script>text</script>", "fixture", "test",
                             frames[0].offset_seconds, frames[-1].offset_seconds, len(frames))


def test_sampling_bounded_and_final_partial_window():
    model = FixtureAnalyzer()
    session = VisionSession(model)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for tick in range(41):
        session.process(frame, tick / 10)
    session.flush()
    assert [[f.offset_seconds for f in window] for window in model.windows] == [[0, .5, 1, 1.5, 2, 2.5, 3, 3.5], [4]]
    decoded = cv2.imdecode(np.frombuffer(model.windows[0][0].jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert max(decoded.shape[:2]) == 512
    assert session.events == []
    assert all(finding['review_required'] for finding in session.findings)


def test_adapter_rejects_bad_input_and_missing_local_model(tmp_path):
    model = SmolVLM2Analyzer(str(tmp_path))
    with pytest.raises(ValueError):
        model.analyze(())
    with pytest.raises(ValueError):
        SampledFrame(b'x', float('nan'))
    with pytest.raises(ValueError):
        model.analyze((SampledFrame(b'x', 2), SampledFrame(b'x', 1)))
    with pytest.raises(RuntimeError, match='not installed'):
        model.analyze((SampledFrame(b'x', 0),))
    # The adapter releases capacity even when loading fails.
    assert model._lock.acquire(blocking=False)
    model._lock.release()


def test_cancelled_recorded_job_does_not_call_model():
    model = FixtureAnalyzer()
    stop = Event()
    stop.set()
    session = VisionSession(model, stop)
    session.process(np.zeros((4, 4, 3), np.uint8), 0)
    with pytest.raises(RuntimeError, match='cancelled'):
        session.flush()
    assert model.windows == []


def test_live_preview_continues_during_analysis(monkeypatch):
    class Capture:
        def isOpened(self): return True
        def read(self):
            time.sleep(.01)
            return True, np.full((4, 4, 3), 100, np.uint8)
        def release(self): pass

    class Blocking(FixtureAnalyzer):
        def analyze(self, frames):
            entered.set()
            release.wait(3)
            return super().analyze(frames)

    entered, release = Event(), Event()
    service = MonitorService()
    camera = Camera('test', 'Test', 0)
    service.add_camera(camera)
    monkeypatch.setattr(cv2, 'VideoCapture', lambda source: Capture())
    worker = CaptureWorker(camera, service, Blocking(), lambda message: None)
    worker._samples.append(sample_frame(np.zeros((4, 4, 3), np.uint8), 0))
    worker._frame_ready.set()
    worker.start()
    try:
        assert entered.wait(2)
        time.sleep(.05)
        first = service.status('test')['last_frame_at']
        time.sleep(.3)
        assert service.status('test')['last_frame_at'] > first
        assert len(worker._samples) <= 8
        assert service.events() == []
    finally:
        release.set()
        worker.stop()
    assert not worker.is_alive()


def test_api_jobs_and_persisted_findings(tmp_path):
    async def check():
        model = FixtureAnalyzer()
        config = tmp_path/'cameras.json'
        config.write_text('{"cameras":[{"id":"cam","name":"Camera","source":0}]}')
        state = str(tmp_path/'state.json')
        app = create_app(str(config), 'fixture-key', state, analyzer=model)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                headers = {'X-API-Key': 'fixture-key', 'X-Filename': 'test.jpg'}
                assert (await client.get('/api/v1/findings')).status_code == 401
                assert (await client.get('/api/v1/findings?camera_id=missing', headers=headers)).status_code == 404
                caps = (await client.get('/api/v1/capabilities', headers=headers)).json()
                assert caps['automatic_alerts'] is True
                assert caps['alert_review_required'] is True
                assert caps['tracker'] == 'disabled'
                assert not any('rule' in item for item in caps['items'])
                _, image = cv2.imencode('.jpg', np.zeros((16, 16, 3), np.uint8))
                response = await client.post('/api/v1/analysis-jobs', headers=headers, content=image.tobytes())
                assert response.status_code == 202
                job_id = response.json()['id']
                for _ in range(100):
                    job = (await client.get(f'/api/v1/analysis-jobs/{job_id}', headers=headers)).json()
                    if job['state'] in {'completed', 'failed'}: break
                    await asyncio.sleep(.02)
                assert job['state'] == 'completed', job
                assert job['findings'][0]['description'].startswith('Fixture')
                legacy = (await client.get(f'/api/v1/algorithm-tests/{job_id}', headers=headers)).json()
                assert legacy['events'] == legacy['detections'] == []
                app.state.service.record_finding('cam', model.analyze((SampledFrame(image.tobytes(), 0),)))
                findings = (await client.get('/api/v1/findings?camera_id=cam', headers=headers)).json()
                assert findings[0]['review_required']
                assert 'confidence' not in findings[0]
        reloaded = create_app(str(config), 'fixture-key', state, analyzer=model)
        assert len(reloaded.state.service.findings('cam')) == 1
        reloaded.state.algorithm_runner.close()
    asyncio.run(check())
