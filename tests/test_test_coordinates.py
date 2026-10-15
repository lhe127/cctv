import asyncio

import cv2
import httpx
import numpy as np

from sentinel.api import create_app
from sentinel.storage import JsonStateStore
from sentinel.vision import VisualFinding


def test_manual_test_location_and_alert_snapshot(tmp_path, monkeypatch):
    monkeypatch.delenv('SENTINEL_ADMIN_API_KEY', raising=False)
    class Analyzer:
        def analyze(self, frames):
            return VisualFinding('Fixture danger', 'fixture', 'test', 0, 0, 1, danger_status='yes')
    state = tmp_path / 'state.json'
    app = create_app(str(tmp_path/'cameras.json'), 'key', str(state), analyzer=Analyzer())
    _, image = cv2.imencode('.jpg', np.zeros((16,16,3), dtype=np.uint8))
    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'X-API-Key':'key'}) as client:
                response = await client.post('/api/v1/cameras', json={'id':'cam','name':'Camera','source':'synthetic','map_position':{'x':2,'y':3}})
                assert response.status_code == 201
                for query in ['map_x=1','map_y=1','map_x=81&map_y=0','map_x=0&map_y=-56',
                              'map_x=nan&map_y=0','map_x=inf&map_y=0','map_x=bad&map_y=1']:
                    response = await client.post('/api/v1/analysis-jobs?'+query, headers={'X-Filename':'test.jpg'}, content=image.tobytes())
                    assert response.status_code == 422, response.text
                assert (await client.get('/api/v1/algorithm-tests')).json() == []
                cases = [('',None), ('map_x=0&map_y=0',{'x':0,'y':0}),
                         ('map_x=-80&map_y=55',{'x':-80,'y':55}),
                         ('camera_id=cam',{'x':2,'y':3}),
                         ('camera_id=cam&map_x=12.5&map_y=-8.25',{'x':12.5,'y':-8.25})]
                for query, expected in cases:
                    response = await client.post('/api/v1/analysis-jobs?'+query, headers={'X-Filename':'test.jpg'}, content=image.tobytes())
                    assert response.status_code == 202, response.text
                    job_id = response.json()['id']
                    for _ in range(200):
                        job = (await client.get('/api/v1/analysis-jobs/'+job_id)).json()
                        if job['state'] in {'completed','failed'}: break
                        await asyncio.sleep(.02)
                    assert job['state'] == 'completed', job
                    assert job.get('map_position') == expected
                    alerts = (await client.get('/api/v1/alerts?status=pending')).json()
                    alert = next(a for a in alerts if a['job_id'] == job_id)
                    assert alert['map_position'] == expected and alert['source'] == 'media_job'
                    if 'camera_id' not in query: assert alert['camera_id'] is None
                assert (await client.get('/api/v1/cameras/cam')).json()['map_position'] == {'x':2,'y':3}
                await client.put('/api/v1/cameras/cam', json={'name':'Moved','map_position':{'x':9,'y':9}})
                assert (await client.get('/api/v1/analysis-jobs/'+job_id)).json()['map_position'] == {'x':12.5,'y':-8.25}
                saved = JsonStateStore(state)
                assert next(a for a in saved.list_alerts() if a['job_id'] == job_id)['map_position'] == {'x':12.5,'y':-8.25}
    asyncio.run(run())
