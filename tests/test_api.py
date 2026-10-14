import unittest
import json
import tempfile
from pathlib import Path

import httpx

from sentinel.api import create_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_zone_update_is_authenticated_and_saved(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            example = Path(directory) / "config.webcam.example.json"
            example.write_text(json.dumps({"cameras": [{"id": "webcam-0", "name": "Webcam", "source": 0,
                                                   "zones": []}]}), encoding="utf-8")
            app = create_app(str(example), "test-key", str(Path(directory) / "state.json"))
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
        with tempfile.TemporaryDirectory(dir=".") as directory:
            app = create_app("config.example.json", "test-key", str(Path(directory) / "state.json"))
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
                self.assertEqual(response.status_code, 410, response.text)
                self.assertEqual(len((await client.get("/api/v1/events", headers=headers)).json()), 0)
                self.assertEqual((await client.get("/api/v1/events?camera_id=gate-2", headers=headers)).json(), [])
                self.assertEqual(len((await client.get("/api/v1/detections", headers=headers)).json()), 0)
                self.assertEqual((await client.get("/api/v1/cameras/gate-1/snapshot", headers=headers)).status_code, 503)
                self.assertEqual((await client.get("/api/v1/cameras/missing/tracks", headers=headers)).status_code, 404)

            reloaded = create_app("config.example.json", "test-key", str(Path(directory) / "state.json"))
            self.assertEqual(len(reloaded.state.service.events()), 0)

    async def test_routed_pages_login_and_camera_crud(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            config = Path(directory) / "cameras.json"
            config.write_text('{"cameras": []}', encoding="utf-8")
            app = create_app(str(config), "test-key", str(Path(directory) / "state.json"))
            transport = httpx.ASGITransport(app=app)
            headers = {"X-API-Key": "test-key"}
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                self.assertEqual((await client.get("/", follow_redirects=False)).headers["location"], "/login")
                for route in ("/login", "/dashboard", "/cameras", "/robots", "/map", "/alerts", "/algorithm-test"):
                    response = await client.get(route)
                    self.assertEqual(response.status_code, 200, route)
                self.assertEqual((await client.post("/api/v1/session")).status_code, 401)
                self.assertEqual((await client.post("/api/v1/session", headers=headers)).json(), {"authenticated": True})

                response = await client.post("/api/v1/cameras", headers=headers,
                    json={"id": "north-gate", "name": "North Gate", "source": 0})
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(response.json()["source_label"], "Webcam 0")
                self.assertEqual((await client.get("/cameras/north-gate")).status_code, 200)
                self.assertEqual((await client.get("/cameras/missing")).status_code, 404)
                self.assertEqual((await client.get("/api/v1/cameras/north-gate")).status_code, 401)
                detail = (await client.get("/api/v1/cameras/north-gate", headers=headers)).json()
                self.assertEqual(detail["id"], "north-gate")
                self.assertNotIn("source", detail)
                response = await client.put("/api/v1/cameras/north-gate", headers=headers,
                    json={"name": "North Entrance"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["name"], "North Entrance")
                self.assertEqual(json.loads(config.read_text())["cameras"][0]["source"], 0)
                self.assertEqual((await client.delete("/api/v1/cameras/north-gate", headers=headers)).status_code, 204)
                self.assertEqual(json.loads(config.read_text())["cameras"], [])

    async def test_algorithm_test_rejects_unsupported_upload(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            app = create_app("config.example.json", "test-key", str(Path(directory) / "state.json"))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/v1/algorithm-tests", content=b"hello",
                    headers={"X-API-Key": "test-key", "X-Filename": "notes.txt", "Content-Type": "text/plain"})
                self.assertEqual(response.status_code, 422)
