import asyncio
import json
from unittest.mock import patch

import httpx
import numpy as np
import pytest

from sentinel.api import create_app
from sentinel.domain import Camera, MapPosition
from sentinel.service import MonitorService
from sentinel.settings import AnalysisSettings, JsonSettingsStore
from sentinel.storage import JsonCameraRepository
from sentinel.video import CaptureWorker
from sentinel.vision import VisualFinding
from sentinel.vision_session import VisionSession


def test_camera_coordinates_and_settings_api(tmp_path, monkeypatch):
    monkeypatch.setenv('SENTINEL_ADMIN_API_KEY', 'admin-test')
    config, state = tmp_path / 'cameras.json', tmp_path / 'state.json'
    app = create_app(str(config), 'operator-test', str(state))

    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                headers = {'X-API-Key': 'operator-test'}
                camera = {'id': 'test', 'name': 'Camera', 'source': 'synthetic', 'map_position': {'x': 0, 'y': 0}}
                assert (await client.post('/api/v1/cameras', json=camera)).status_code == 401
                response = await client.post('/api/v1/cameras', headers=headers, json=camera)
                assert response.status_code == 201
                assert response.json()['map_position'] == {'x': 0, 'y': 0}
                response = await client.put('/api/v1/cameras/test', headers=headers, json={'name': 'Renamed'})
                assert response.json()['map_position'] == {'x': 0, 'y': 0}
                for position in ({'x': 81, 'y': 0}, {'x': 0, 'y': -56}, {'x': 0}):
                    response = await client.put('/api/v1/cameras/test', headers=headers,
                                                json={'name': 'Renamed', 'map_position': position})
                    assert response.status_code == 422
                assert JsonCameraRepository(config).load()[0].map_position == MapPosition(0, 0)
                response = await client.put('/api/v1/cameras/test', headers=headers,
                                            json={'name': 'Renamed', 'map_position': None})
                assert response.json()['map_position'] is None
                assert JsonCameraRepository(config).load()[0].map_position is None
                assert (await client.get('/api/v1/settings')).status_code == 401
                assert (await client.get('/api/v1/settings', headers=headers)).status_code == 403
                admin = {**headers, 'X-Admin-Key': 'admin-test'}
                value = (await client.get('/api/v1/settings', headers=admin)).json()
                value.update(prompt='Describe visible motion only.', sample_fps=1, window_frames=3, max_new_tokens=64)
                assert (await client.put('/api/v1/settings', headers=headers, json=value)).status_code == 403
                assert (await client.put('/api/v1/settings', headers=admin, json=value)).status_code == 200
                for field, invalid in [('prompt', ' '), ('sample_fps', 0), ('window_frames', 9), ('preview_fps', 16), ('max_new_tokens', 257)]:
                    assert (await client.put('/api/v1/settings', headers=admin, json={**value, field: invalid})).status_code == 422
                assert JsonSettingsStore(tmp_path / 'state-settings.json').get().model_dump() == value
                assert (await client.get('/api/v1/capabilities', headers=headers)).json()['inference_fps'] == 1
                assert (await client.get('/settings')).status_code == 200
    asyncio.run(run())


def test_settings_atomic_failure_keeps_previous_snapshot(tmp_path):
    store = JsonSettingsStore(tmp_path / 'settings.json')
    original = store.get()
    store.save(original)
    with patch('sentinel.settings.os.replace', side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError):
            store.save(AnalysisSettings(sample_fps=1))
    assert store.get() == original
    assert JsonSettingsStore(store.path).get() == original


def test_configured_sampling_and_live_queue():
    class Analyzer:
        def __init__(self): self.windows = []
        def analyze(self, frames):
            self.windows.append(frames)
            return VisualFinding('Fixture', 'fixture', 'test', frames[0].offset_seconds, frames[-1].offset_seconds, len(frames))
    settings = AnalysisSettings(sample_fps=1, window_frames=3, preview_fps=7)
    analyzer = Analyzer()
    session = VisionSession(analyzer, settings=settings)
    for tick in range(41):
        session.process(np.zeros((4, 4, 3), dtype=np.uint8), tick / 10)
    session.flush()
    assert [[frame.offset_seconds for frame in window] for window in analyzer.windows] == [[0, 1, 2], [3, 4]]
    worker = CaptureWorker(Camera('test', 'test', 0), MonitorService(), analyzer, lambda _: None, settings=settings)
    assert worker._samples.maxlen == 3
    assert worker.sample_interval == 1
    assert worker.preview_fps == 7


def test_legacy_coordinates_remain_unplaced(tmp_path):
    config = tmp_path / 'cameras.json'
    config.write_text(json.dumps({'cameras': [{'id': 'old', 'name': 'Old', 'source': 0}]}))
    assert JsonCameraRepository(config).load()[0].map_position is None
    with pytest.raises(ValueError):
        MapPosition(float('nan'), 0)


def test_prompt_and_token_settings_reach_model_call(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from sentinel.smolvlm import SmolVLM2Analyzer
    from sentinel.vision import sample_frame
    store = JsonSettingsStore(tmp_path / 'settings.json')
    calls = []
    class Inputs(dict):
        def to(self, device): return self
    class Processor:
        def apply_chat_template(self, messages, **kwargs):
            calls.append(messages[0]['content'][1]['text'])
            return 'fixture'
        def __call__(self, **kwargs): return Inputs(input_ids=np.array([[1]]))
        def batch_decode(self, output, **kwargs): return ['Visible scene']
    def generate(**kwargs):
        calls.append(kwargs['max_new_tokens'])
        return np.array([[1, 2]])
    monkeypatch.setitem(__import__('sys').modules, 'torch', SimpleNamespace(inference_mode=nullcontext))
    analyzer = SmolVLM2Analyzer(settings_provider=store.get)
    analyzer._model = SimpleNamespace(device='cpu', generate=generate)
    analyzer._processor = Processor()
    frame = sample_frame(np.zeros((4, 4, 3), dtype=np.uint8), 0)
    for prompt, tokens in [('First prompt', 32), ('Second prompt', 64)]:
        store.save(AnalysisSettings(prompt=prompt, max_new_tokens=tokens))
        analyzer.analyze((frame,))
    assert calls == ['First prompt', 32, 'Second prompt', 64]
