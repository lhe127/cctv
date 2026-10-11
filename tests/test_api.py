import unittest
import json
import tempfile
from pathlib import Path

import httpx

from sentinel.api import create_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_zone_update_is_authenticated_and_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            example = Path(directory) / "config.webcam.example.json"
            example.write_text(json.dumps({"cameras": [{"id": "webcam-0", "name": "Webcam", "source": 0,
                                                   "zones": []}]}), encoding="utf-8")
            app = create_app(str(example), "test-key")
            transport = httpx.ASGITransport(app=app)
            zone = {"id": "door", "rule": "door_tampering",
                    "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.9], [0.1, 0.9]]}
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                path = "/api/v1/cameras/webcam-0/zones"
                self.assertEqual((await client.put(path, json=[zone])).status_code, 401)
                headers = {"X-API-Key": "test-key"}
                response = await client.put(path, json=[zone], headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["saved_to"], "config.local.json")
                self.assertEqual((await client.get("/api/v1/cameras", headers=headers)).json()[0]["zones"][0]["id"], "door")
                self.assertEqual(json.loads((Path(directory) / "config.local.json").read_text())
                                 ["cameras"][0]["zones"][0]["id"], "door")
                self.assertEqual((await client.put(path, json=[zone, zone], headers=headers)).status_code, 422)
                self.assertEqual((await client.put(path, json=[{**zone, "polygon": [[0, 0], [2, 0], [0, 1]]}],
                                                   headers=headers)).status_code, 422)

    async def test_auth_and_virtual_observation(self):
        app = create_app("config.example.json", "test-key")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            self.assertEqual((await client.get("/health")).status_code, 200)
            self.assertEqual((await client.get("/api/v1/cameras")).status_code, 401)
            headers = {"X-API-Key": "test-key"}
            cameras = (await client.get("/api/v1/cameras", headers=headers)).json()
            self.assertEqual(len(cameras), 2)
            self.assertNotIn("source", cameras[0])
            self.assertEqual((await client.get("/api/v1/cameras/gate-1/status", headers=headers)).json()["state"], "stopped")
            self.assertEqual((await client.post("/api/v1/cameras/gate-1/start", headers=headers)).status_code, 422)
            response = await client.post("/api/v1/cameras/gate-1/observations", headers=headers,
                json={"detections": [{"kind": "person", "box": [0.2, 0.3, 0.3, 0.65], "confidence": 0.9}]})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()["events"]), 1)
            self.assertEqual(len((await client.get("/api/v1/events", headers=headers)).json()), 1)
            self.assertEqual(len((await client.get("/api/v1/detections", headers=headers)).json()), 1)
            self.assertEqual((await client.get("/api/v1/cameras/gate-1/snapshot", headers=headers)).status_code, 503)
            self.assertEqual((await client.get("/api/v1/cameras/missing/tracks", headers=headers)).status_code, 404)
