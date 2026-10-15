import asyncio
import json
from dataclasses import replace
from unittest.mock import patch

import cv2
import httpx
import numpy as np
import pytest

from sentinel.alerts import AlertService
from sentinel.api import create_app
from sentinel.domain import Camera, MapPosition
from sentinel.smolvlm import parse_danger_result
from sentinel.storage import JsonStateStore
from sentinel.vision import VisualFinding


@pytest.mark.parametrize(('output', 'status'), [
    ('DANGER: yes\nA person is visibly punching another person.', 'yes'),
    ('DANGER: no\nPeople are walking. No fighting is visible.', 'no'),
    ('DANGER: uncertain\nContact is obscured.', 'uncertain'),
    ('People might be fighting.', 'uncertain'),
    ('No dangerous actions or fighting.', 'uncertain'),
    ('DANGER: yes', 'uncertain'),
    ('DANGER: yes\n   ', 'uncertain'),
    ('DANGER: yes\nVisible contact.\nDANGER: no', 'uncertain'),
    ('DANGER: yes\nVisible contact.\n  DANGER: no', 'uncertain'),
    ('{"danger": true}', 'uncertain'),
    ('ANGER : yes, DANGER : no.', 'uncertain'),
    ('DANGER : yes, DANGER : no.', 'uncertain'),
    ('danger : YES\nEVIDENCE: Flames spread across the roof.', 'yes'),
    ('ANGER : yes\nFlames are coming from the house.', 'yes'),
    ('DANGER : no\nEVIDENCE: No flames are visible.', 'no'),
    ('DANGER: yes/no', 'uncertain'),
    ('DANGER: yes\nEVIDENCE: [visible observation]', 'uncertain'),
])
def test_explicit_danger_contract(output, status):
    assert parse_danger_result(output)[0] == status


def finding(status='yes'):
    return VisualFinding('Fixture danger <script>not code</script>', 'fixture', 'revision', 0, 3.5, 8,
                         danger_status=status)


def test_idempotent_alert_lifecycle_and_location_snapshot(tmp_path):
    store = JsonStateStore(tmp_path / 'state.json', max_events=1)
    service = AlertService(store)
    camera = Camera('cam', 'Gate', 'synthetic', map_position=MapPosition(12, -8))
    item = {**finding().public(), 'id': 'finding-1'}
    alert = service.record_finding(item, camera)
    assert alert['map_position'] == {'x': 12, 'y': -8}
    assert service.record_finding({**item, 'danger_status': 'no'}, camera) is None
    assert service.record_finding({**item, 'danger_status': 'uncertain'}, camera) is None
    resolved = service.set_status(alert['id'], 'resolved')
    assert resolved['resolved_at'] and not service.list('pending')
    duplicate = service.record_finding(item, replace(camera, map_position=MapPosition(0, 0)))
    assert duplicate == resolved  # retries neither reopen nor relocate an incident
    assert service.set_status(alert['id'], 'resolved') == resolved
    assert len(service.list()) == 1
    reopened = service.set_status(alert['id'], 'pending')
    assert reopened['resolved_at'] is None
    assert AlertService(JsonStateStore(store.path)).list() == [reopened]
    service.record_finding({**item, 'id': 'finding-2'})
    assert len(service.list('pending')) == 2  # pending alerts must not be silently truncated
    assert service.list()[0]['map_position'] is None
    with patch.object(store, '_write', side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError):
            service.set_status('finding-1', 'resolved')
    assert len(service.list('pending')) == 2


def test_alert_end_to_end_api_and_media_job(tmp_path):
    class Analyzer:
        def analyze(self, frames): return finding()

    config = tmp_path / 'cameras.json'
    config.write_text(json.dumps({'cameras': [{'id': 'cam', 'name': 'Gate', 'source': 'synthetic',
                                              'map_position': {'x': 0, 'y': 0}}]}))
    state = tmp_path / 'state.json'
    app = create_app(str(config), 'test-key', str(state), analyzer=Analyzer())

    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                headers = {'X-API-Key': 'test-key'}
                app.state.service.record_finding('cam', finding('no'))
                app.state.service.record_finding('cam', finding('uncertain'))
                assert app.state.alert_service.list() == []
                app.state.service.record_finding('cam', finding())
                assert (await client.get('/api/v1/alerts')).status_code == 401
                response = await client.get('/api/v1/alerts?status=pending', headers=headers)
                assert response.status_code == 200
                alert = response.json()[0]
                assert alert['map_position'] == {'x': 0, 'y': 0}
                assert alert['review_required'] and alert['source'] == 'camera'
                path = '/api/v1/alerts/' + alert['id']
                assert (await client.patch(path, json={'status': 'resolved'})).status_code == 401
                assert (await client.patch(path, headers=headers, json={'status': 'other'})).status_code == 422
                assert (await client.get('/api/v1/alerts?status=other', headers=headers)).status_code == 422
                assert (await client.patch('/api/v1/alerts/missing', headers=headers, json={'status': 'resolved'})).status_code == 404
                assert (await client.patch(path, headers=headers, json={'status': 'resolved'})).status_code == 200
                assert (await client.get('/api/v1/alerts?status=pending', headers=headers)).json() == []
                assert (await client.get('/api/v1/summary', headers=headers)).json()['alert_count'] == 0
                assert (await client.patch(path, headers=headers, json={'status': 'pending'})).json()['resolved_at'] is None
                _, image = cv2.imencode('.jpg', np.zeros((16, 16, 3), dtype=np.uint8))
                for suffix in ('?camera_id=cam', ''):
                    response = await client.post('/api/v1/analysis-jobs' + suffix,
                        headers={**headers, 'X-Filename': 'fixture.jpg'}, content=image.tobytes())
                    assert response.status_code == 202
                    job_id = response.json()['id']
                    for _ in range(100):
                        job = (await client.get('/api/v1/analysis-jobs/' + job_id, headers=headers)).json()
                        if job['state'] in {'completed', 'failed'}: break
                        await asyncio.sleep(.02)
                    assert job['state'] == 'completed', job
                    assert job['findings'][0]['danger_status'] == 'yes'
                alerts = (await client.get('/api/v1/alerts?status=pending', headers=headers)).json()
                assert len(alerts) == 3
                assert alerts[0]['source'] == 'media_job' and alerts[0]['map_position'] is None
                assert alerts[1]['map_position'] == {'x': 0, 'y': 0}
                assert (await client.get('/api/v1/summary', headers=headers)).json()['alert_count'] == 3
        reloaded = create_app(str(config), 'test-key', str(state), analyzer=Analyzer())
        async with reloaded.router.lifespan_context(reloaded):
            assert len(reloaded.state.alert_service.list('pending')) == 3
    asyncio.run(run())
