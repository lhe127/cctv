"""Post deterministic virtual detections to a running API without third-party packages."""
import json
import os
from time import sleep, time
from urllib.request import Request, urlopen

base = os.getenv("SENTINEL_URL", "http://127.0.0.1:8000")
key = os.environ["SENTINEL_API_KEY"]
for step in range(16):
    camera = "gate-1" if step % 2 == 0 else "gate-2"
    x = 0.2 if camera == "gate-1" else 0.6
    body = json.dumps({"at": time(), "detections": [{"kind": "person", "box": [x, 0.3, x + 0.1, 0.65], "confidence": 0.94}]}).encode()
    req = Request(f"{base}/api/v1/cameras/{camera}/observations", body, {"Content-Type": "application/json", "X-API-Key": key})
    with urlopen(req, timeout=5) as response:
        print(camera, response.status, json.load(response)["events"])
    sleep(1)
