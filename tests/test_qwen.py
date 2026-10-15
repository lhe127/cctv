import asyncio
import json

import httpx
import pytest

from sentinel.api import create_app
from sentinel.qwen import QwenAnalyzer, ConfiguredAnalyzer
from sentinel.settings import AnalysisSettings, JsonSettingsStore, SettingsUpdate
from sentinel.vision import SampledFrame


class Connection:
    status = 200
    result = {"choices": [{"message": {"content": "DANGER: yes\nEVIDENCE: Flames on the roof."}, "finish_reason": "stop"}]}
    def __init__(self, host, timeout):
        self.host, self.timeout, self.closed = host, timeout, False
    def request(self, method, path, body, headers):
        self.body, self.headers = json.loads(body), headers
    def getresponse(self): return self
    def read(self, limit): return json.dumps(self.result).encode()
    def close(self): self.closed = True


def settings(**kwargs):
    return AnalysisSettings(qwen_enabled=True, qwen_workspace="workspace123", qwen_api_key="private-test-key", **kwargs)


def test_cloud_frames_prompt_and_switch():
    connections = []
    def factory(*args, **kwargs):
        c = Connection(*args, **kwargs)
        connections.append(c)
        return c
    value = settings(prompt="Visible fire is danger.")
    class Local:
        def analyze(self, frames, *, settings): return "local"
    router = ConfiguredAnalyzer(lambda: value, Local(), QwenAnalyzer(factory))
    frames = (SampledFrame(b"jpeg1", 0), SampledFrame(b"jpeg2", .5))
    result = router.analyze(frames)
    assert result.danger_status == "yes" and result.frames_analyzed == 2
    c = connections[0]
    assert c.host == "workspace123.ap-southeast-1.maas.aliyuncs.com" and c.closed
    assert c.headers['Authorization'] == 'Bearer private-test-key'
    content = c.body['messages'][0]['content']
    assert content[0]['text'].startswith(value.prompt)
    assert len([p for p in content if p['type'] == 'image_url']) == 2
    assert content[3]['text'] == 'Frame at 0.500 seconds:'
    value = AnalysisSettings()
    assert router.analyze(frames) == 'local' and len(connections) == 1


@pytest.mark.parametrize('status,result,expected', [
    (401, {}, 'error'), (429, {}, 'error'), (302, {}, 'error'),
    (200, {}, 'error'),
    (200, {'choices': [{'message': {'content': 'ANGER: yes, DANGER: no'}, 'finish_reason': 'stop'}]}, 'uncertain'),
    (200, {'choices': [{'message': {'content': 'DANGER: yes\nEVIDENCE: flames'}, 'finish_reason': 'length'}]}, 'uncertain'),
])
def test_cloud_failures(status, result, expected):
    c = Connection('unused', 5)
    c.status, c.result = status, result
    model = QwenAnalyzer(lambda *a, **k: c)
    if expected == 'error':
        with pytest.raises(RuntimeError): model.analyze((SampledFrame(b'jpeg', 0),), settings=settings())
    else:
        finding = model.analyze((SampledFrame(b'jpeg', 0),), settings=settings())
        assert finding.danger_status == expected and finding.analysis_warning
    assert c.closed


def test_timeout_is_sanitized():
    class Timeout(Connection):
        def request(self, *a, **k): raise TimeoutError('private-test-key')
    with pytest.raises(RuntimeError, match='timed out') as error:
        QwenAnalyzer(Timeout).analyze((SampledFrame(b'jpeg', 0),), settings=settings())
    assert 'private-test-key' not in str(error.value)


def test_settings_secret_persistence_and_redaction(tmp_path, monkeypatch):
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
    monkeypatch.delenv('SENTINEL_ADMIN_API_KEY', raising=False)
    state = tmp_path / 'state.json'
    app = create_app(str(tmp_path / 'cameras.json'), 'owner', str(state))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'X-API-Key':'owner'}) as client:
            assert (await client.put('/api/v1/settings', json={'qwen_enabled':True})).status_code == 422
            data = {'qwen_enabled':True, 'qwen_workspace':'workspace123', 'qwen_api_key':'private-test-key'}
            response = await client.put('/api/v1/settings', json=data)
            assert response.status_code == 200, response.text
            assert 'private-test-key' not in response.text and response.json()['qwen_key_configured']
            response = await client.get('/api/v1/settings')
            assert 'qwen_api_key' not in response.json()
            for invalid in ({**data, 'qwen_timeout':0}, {**data,'qwen_api_key':{'bad':'private-test-key'}}):
                response = await client.put('/api/v1/settings', json=invalid)
                assert response.status_code == 422 and 'private-test-key' not in response.text
            data.pop('qwen_api_key')
            assert (await client.put('/api/v1/settings', json=data)).status_code == 200
            store = JsonSettingsStore(tmp_path / 'state-settings.json')
            assert store.get().qwen_api_key.get_secret_value() == 'private-test-key'
            response = await client.put('/api/v1/settings', json={'clear_qwen_api_key':True})
            assert response.status_code == 200 and not response.json()['qwen_key_configured']
            assert not JsonSettingsStore(store.path).get().qwen_api_key.get_secret_value()
    asyncio.run(run())
