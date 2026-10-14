"""Bounded webcam-to-API smoke check. Reads frames in memory and saves resulting review findings."""
import asyncio
import os

import httpx

from sentinel.api import create_app


async def main() -> None:
    key = os.environ["SENTINEL_API_KEY"]
    app = create_app(os.getenv("SENTINEL_CONFIG", "config.webcam.example.json"), key)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            headers = {"X-API-Key": key}
            started = await client.post("/api/v1/cameras/webcam-0/start", headers=headers)
            started.raise_for_status()
            try:
                for _ in range(480):
                    response = await client.get("/api/v1/cameras/webcam-0/snapshot", headers=headers)
                    if response.status_code == 200:
                        if response.headers.get("content-type") != "image/jpeg" or not response.content.startswith(b"\xff\xd8"):
                            raise RuntimeError("snapshot was not a JPEG")
                        state = (await client.get("/api/v1/cameras/webcam-0/status", headers=headers)).json()
                        if state["state"] == "error":
                            raise RuntimeError(state["error"])
                        if state["last_observation_at"] is not None:
                            detections = (await client.get("/api/v1/findings", headers=headers)).json()
                            print(f"Webcam-to-API check passed: {len(response.content)} JPEG bytes; "
                                  f"detector={state['detector']}; findings={len(detections)}")
                            return
                    await asyncio.sleep(0.25)
                raise RuntimeError("webcam snapshot or detector observation unavailable after 120 seconds")
            finally:
                stopped = await client.post("/api/v1/cameras/webcam-0/stop", headers=headers)
                stopped.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
