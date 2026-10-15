"""Exercise both real application paths with a fixture model runtime (not an accuracy test)."""
import asyncio
from contextlib import nullcontext
import json
from types import SimpleNamespace

import cv2
import httpx
import numpy as np
import pytest
from sentinel.qwen import QwenAnalyzer

from sentinel.api import create_app
from sentinel.smolvlm import ALERT_FORMAT


@pytest.mark.parametrize('cloud', [False, True])
def test_shared_prompt_updates_camera_and_algorithm_alerts(tmp_path, monkeypatch, cloud):
    monkeypatch.delenv('SENTINEL_ADMIN_API_KEY', raising=False)
    monkeypatch.setitem(__import__('sys').modules, 'torch', SimpleNamespace(inference_mode=nullcontext))
    criteria = {
        'Danger means a person visibly entering the pool. Walking is not danger.': 'yes',
        'Danger means visible fire only. Entering the pool is not danger.': 'no',
        'Danger means crossing a boundary that cannot be seen in these frames.': 'uncertain',
    }
    calls = []

    class Inputs(dict):
        def to(self, device): return self

    class Processor:
        def apply_chat_template(self, messages, **kwargs):
            self.prompt = messages[0]['content'][1]['text']
            calls.append(self.prompt)
            return self.prompt

        def __call__(self, **kwargs):
            return Inputs(input_ids=np.array([[1]]))

        def batch_decode(self, output, **kwargs):
            prompt = self.prompt.removesuffix(ALERT_FORMAT)
            return [f'DANGER: {criteria[prompt]}\nFixture evidence evaluated for the configured criteria.']

    _, image = cv2.imencode('.jpg', np.zeros((16, 16, 3), dtype=np.uint8))
    camera_file = tmp_path / 'camera.jpg'
    camera_file.write_bytes(image.tobytes())
    config = tmp_path / 'cameras.json'
    config.write_text(json.dumps({'cameras': [{'id': 'cam', 'name': 'Fixture camera', 'source': str(camera_file)}]}))
    app = create_app(str(config), 'test-key', str(tmp_path / 'state.json'))
    # Keep the application's real settings provider, shared adapter, workers and alert callbacks.
    model = app.state.algorithm_runner.analyzer_factory()
    assert model is app.state.controller.analyzer_factory()
    class CloudConnection:
        status = 200
        def __init__(self, *args, **kwargs): pass
        def request(self, method, path, body, headers):
            content = json.loads(body)['messages'][0]['content']
            assert any(item['type'] == 'image_url' for item in content)
            self.prompt = next(prompt for prompt in criteria if content[0]['text'].startswith(prompt))
            calls.append(self.prompt + ALERT_FORMAT)
        def getresponse(self): return self
        def read(self, limit):
            return json.dumps({'choices':[{'message':{'content':f'DANGER: {criteria[self.prompt]}\nEVIDENCE: Fixture observation.'},'finish_reason':'stop'}]}).encode()
        def close(self): pass
    model.cloud = QwenAnalyzer(CloudConnection)
    model = model.local
    model._model = SimpleNamespace(device='cpu', generate=lambda **kwargs: np.array([[1, 2]]))
    model._processor = Processor()

    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                headers = {'X-API-Key': 'test-key'}
                for index, (prompt, decision) in enumerate(criteria.items()):
                    response = await client.put('/api/v1/settings', headers=headers,
                        json={'prompt': prompt, 'window_frames': 1, 'qwen_enabled':cloud,
                              'qwen_workspace':'fixture', 'qwen_api_key':'fixture-key'})
                    assert response.status_code == 200, response.text
                    response = await client.post('/api/v1/cameras/cam/start', headers=headers)
                    assert response.status_code == 200, response.text
                    for _ in range(200):
                        findings = (await client.get('/api/v1/findings', headers=headers)).json()
                        if len(findings) == index + 1: break
                        await asyncio.sleep(.02)
                    assert len(findings) == index + 1
                    assert findings[0]['danger_status'] == decision
                    assert (await client.post('/api/v1/cameras/cam/stop', headers=headers)).status_code == 200
                    response = await client.post('/api/v1/analysis-jobs',
                        headers={**headers, 'X-Filename': 'fixture.jpg'}, content=image.tobytes())
                    assert response.status_code == 202
                    job_id = response.json()['id']
                    for _ in range(200):
                        job = (await client.get('/api/v1/analysis-jobs/' + job_id, headers=headers)).json()
                        if job['state'] in {'completed', 'failed'}: break
                        await asyncio.sleep(.02)
                    assert job['state'] == 'completed', job
                    assert job['findings'][0]['danger_status'] == decision
                    alerts = (await client.get('/api/v1/alerts', headers=headers)).json()
                    assert len(alerts) == 2  # Only the first criteria produced yes in both paths.
                    assert {alert['source'] for alert in alerts} == {'camera', 'media_job'}
                    assert all(alert['status'] == 'pending' for alert in alerts)
        assert calls == [prompt + ALERT_FORMAT for prompt in criteria for _ in range(2)]
        assert 'punching' not in ALERT_FORMAT and 'Ordinary walking' not in ALERT_FORMAT

    asyncio.run(run())
