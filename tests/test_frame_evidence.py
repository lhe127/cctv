"""Evidence must be the exact model input, not a guessed frame from the preview."""
import asyncio

import cv2
import httpx
import numpy as np
import pytest

from sentinel.api import create_app
from sentinel.vision import VisualFinding


@pytest.mark.parametrize('video', [False, True])
def test_evidence_frames_api(tmp_path, monkeypatch, video):
    monkeypatch.delenv('SENTINEL_ADMIN_API_KEY', raising=False)
    inputs = []
    class Analyzer:
        def analyze(self, frames):
            inputs.append(frames)
            return VisualFinding('Visible fixture hazard', 'fixture', 'test', frames[0].offset_seconds,
                                 frames[-1].offset_seconds, len(frames), danger_status='yes')
    if video:
        path = tmp_path / 'clip.avi'
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 4, (32, 32))
        assert writer.isOpened()
        for index in range(10): writer.write(np.full((32, 32, 3), index * 20, dtype=np.uint8))
        writer.release()
        payload, name = path.read_bytes(), 'clip.avi'
    else:
        _, encoded = cv2.imencode('.jpg', np.zeros((32,32,3), dtype=np.uint8))
        payload, name = encoded.tobytes(), 'image.jpg'
    app = create_app(str(tmp_path/'cameras.json'), 'test-key', str(tmp_path/'state.json'), analyzer=Analyzer())
    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                headers = {'X-API-Key':'test-key'}
                await client.put('/api/v1/settings', headers=headers, json={'window_frames':3})
                response = await client.post('/api/v1/analysis-jobs', headers={**headers,'X-Filename':name}, content=payload)
                job_id = response.json()['id']
                for _ in range(300):
                    job = (await client.get('/api/v1/analysis-jobs/'+job_id, headers=headers)).json()
                    if job['state'] in {'completed','failed'}: break
                    await asyncio.sleep(.02)
                assert job['state'] == 'completed', job
                assert len(inputs) == len(job['findings'])
                for index, frames in enumerate(inputs):
                    assert job['findings'][index]['evidence_frames'] == [{'offset_seconds':f.offset_seconds} for f in frames]
                    for frame_index, frame in enumerate(frames):
                        url = f'/api/v1/analysis-jobs/{job_id}/findings/{index}/frames/{frame_index}'
                        assert (await client.get(url)).status_code == 401
                        response = await client.get(url, headers=headers)
                        assert response.status_code == 200
                        assert response.content == frame.jpeg
                        assert response.headers['cache-control'] == 'private, no-store'
                base = f'/api/v1/analysis-jobs/{job_id}/findings/'
                for suffix in ['-1/frames/0','999/frames/0','0/frames/-1','0/frames/999']:
                    assert (await client.get(base+suffix, headers=headers)).status_code == 404
                saved = app.state.algorithm_runner.evidence_frame(job_id,0,0)
                saved.unlink()  # Verify explicit missing-evidence response, not a replacement frame.
                assert (await client.get(base+'0/frames/0', headers=headers)).status_code == 410
    asyncio.run(run())
