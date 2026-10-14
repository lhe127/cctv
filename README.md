# Township Sentinel

Virtual-first prototype for A01–A08 CCTV monitoring. The engineering rules for future work are in [AGENTS.md](AGENTS.md).

## Implemented scope

| ID | Capability | Current behavior |
|---|---|
| A01 | CCTV live streaming | Start/stop a configured webcam, video file, or RTSP source from the dashboard; authenticated MJPEG and snapshot endpoints expose the latest frame. |
| A02 | Multi-camera monitoring | One isolated capture worker and tracker per camera; dashboard displays all configured cameras. |
| A03 | Human detection and tracking | Pinned OpenCV Zoo YOLOX-S model detects people; centroid tracker assigns temporary IDs. Virtual detections still work without a model. |
| A04 | Vehicle detection and tracking | Same model detects COCO car, motorcycle, bus, and truck classes as vehicles. |
| A05 | Restricted-area intrusion | A person entering a normalized polygon creates a cooldown-controlled alert. |
| A06 | Loitering | A person remaining in a polygon for the configured dwell time creates an alert. |
| A07 | Wall climbing | Sustained upward person movement in a wall zone creates a **suspected** alert. An optional `crossing_line_y` requires the person's lower box edge to cross a marked fence-top line. |
| A08 | Door tampering | A small handle-zone polygon measures sustained local motion while surrounding scene motion stays low. It can report a **suspected** handle-activity alert without a full person detection. It does not establish tampering or intent. |

The local management console now provides distinct `/dashboard`, `/cameras`, `/robots`, `/map`, `/alerts`, and `/algorithm-test` routes. It includes API-key sign-in, camera CRUD, semantic polygon drawing, persistent alert history, an offline interactive 3D residential site model, and queued image/video detector testing. The robot page is an explicit integration-ready empty state; it does not pretend that hardware is connected.

Download the pinned Apache-2.0 model with `scripts/download_yolox.py` before starting real-video detection. Model bytes are excluded from source control. A07/A08 are review signals, not reliable behavior classifiers. A08 can still mistake ordinary handle use for suspicious activity. Alerts must be checked by a human before action.

## Run locally

Install Python 3.11+ and dependencies in your normal environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[video,test]'
.\.venv\Scripts\python.exe scripts/download_yolox.py
$env:SENTINEL_API_KEY='replace-with-a-long-local-secret'
$env:SENTINEL_CONFIG='config.webcam.example.json'
# Optional; defaults to data/sentinel-state.json
$env:SENTINEL_DATA_FILE='data/sentinel-state.json'
.\.venv\Scripts\python.exe -m sentinel.api
```

Open `http://127.0.0.1:8000/`. The server redirects to `/login`; enter the same API key to open the dashboard. The key is held in browser `sessionStorage`, is sent as `X-API-Key`, and is cleared by **Sign out**. This is a local shared-secret gate, not user identity or production session management. API documentation is at `/docs`.

Use **Cameras** to create a camera, then **Open camera** to visit its `/cameras/{camera_id}` detail page. Start/stop, edit, delete, live preview, and zone drawing are on this page, with camera-specific alert history below. Behavior tiles highlight alerts from the last ten seconds only while frames are live. Fire and fall are explicitly marked **Not installed**; no fire/fall classifier is bundled. Camera credentials are never returned by the API; the UI shows only a sanitized source label. To calibrate A05–A08, select **Draw zones**, choose an existing zone or create one, click **Draw new shape**, mark at least three points, choose the area's meaning and detection rule, save the draft, then save all zones. The authenticated API updates the running camera immediately and writes `config.local.json` when the server was started from an example config. On the next server start, set `SENTINEL_CONFIG=config.local.json` so the saved cameras and zones load. Editing an explicitly named private config writes back to that file. Zone changes reset current tracks for that camera; they do not erase prior alerts.

The **Algorithm test** route accepts JPG, PNG, WEBP, MP4, MOV, AVI, and MKV uploads up to 100 MB. Work runs on a one-job background executor so inference does not block the API event loop. Images produce an annotated JPEG. Videos produce browser-playable VP8/WebM without audio, sample detection at up to roughly five frames per second, and are bounded to the first 60 seconds. Old MP4 results are converted on first viewing; their original files are retained. The installed OpenCV build must support VP8 encoding. Job metadata and outputs are stored under the configured state directory. Tests currently exercise object detection, not the camera-specific zone/temporal behavior rules. Treat these results as review signals, not accuracy certification.

Alerts and algorithm-test metadata are stored atomically in `data/sentinel-state.json` by default; annotated test output is stored in `data/algorithm-results/`. The `data/` directory is ignored by Git. Set `SENTINEL_DATA_FILE` to move state elsewhere. Back up or delete that local directory according to the deployment's retention policy.

The browser preview refreshes independently of inference at up to five frames per second, with only one snapshot request in flight. JPEG production defaults to 5 FPS (`SENTINEL_PREVIEW_FPS`, range 1–15); camera object inference defaults to 2 FPS (`SENTINEL_INFERENCE_FPS`, range 0.5–10). Set these environment variables before starting the server; the browser remains capped at 5 FPS. The capture worker continues draining the source and retains only the newest frame, so slow CPU inference does not build a backlog. Lower rates reduce load but can miss brief actions. Detection boxes can trail moving subjects; CPU speed and model choice determine detection latency.

Terminal logs include timestamped camera start/stop requests, state changes, emitted alerts, and algorithm job progress. `SENTINEL_LOG_LEVEL` defaults to `INFO`. Logs omit camera source credentials and API keys. Restart the server after changing settings or updating code.

The **Residential map** route renders the supplied master-plan layout as a WebGL architectural scene with textured tiled roofs, framed glass windows, porches, cars, landscaping, pool furniture, sunlight, and cast shadows. Locally bundled Three.js 0.180.0 supplies physically based materials, perspective, picking, and orbit controls; no CDN access is needed at runtime. WebGL 2 and browser hardware acceleration are required. Drag to orbit, right-drag to pan, scroll or pinch to zoom, and select a model, label, or directory entry for details. Arrow keys orbit, +/- zoom, and Home resets the view. Scene resources are released when leaving the page. Rendering is demand-driven; there is no continuous water animation. Camera locations and coverage are illustrative planning markers, not GPS positions or calibrated fields of view. Building elevations, dimensions, and materials are interpretations because the supplied image is a plan, not a survey or architectural specification. No site-map data is sent to a third-party service. The rendering decision and replacement boundary are documented in [ADR 004](docs/adr-004-architectural-map.md).

If port 8000 is already in use, set `SENTINEL_PORT=8001` before starting the server and open `http://127.0.0.1:8001/` instead.

To simulate two cameras without hardware, use `config.example.json` and run `python scripts/simulate.py` in another terminal with the same API key. Virtual tracks and alerts appear in the dashboard.

Local evaluation videos belong in `media/test-clips/`, which is ignored by source control. To try one, copy the webcam config to `config.local.json`, replace its numeric `source` with `media/test-clips/climbing-video.mp4` or `media/test-clips/open-door-video.mp4`, and start the server with `SENTINEL_CONFIG=config.local.json` from the project root. Set zones for the selected video's actual view; the illustrative webcam polygons will not match it.

Local files play at their recorded frame rate and stop at the end. Press **Start camera + detection** again to replay. Detection runs independently and may skip frames on a slow CPU.

After installing the model, run `python scripts/evaluate_clips.py` to repeat the small offline regression check. It samples the climbing clip at one-second intervals and the ordinary-opening and staged lock-tool clips at half-second intervals using fixed example zones. The annotated windows are documented in [clip evaluation notes](docs/clip-evaluation.md). This is a regression check, not an accuracy estimate for CCTV deployment.

To replay the staged lock-tool clip in the dashboard, set `$env:SENTINEL_CONFIG='config.tampering.example.json'` before starting the server, then click **Start camera + detection**. This [example config](config.tampering.example.json) uses a lock zone calibrated only for that video and more sensitive demonstration thresholds. A08 samples door motion about twice per second in the capture worker, independently of slower person inference. Existing webcam zones should be calibrated separately.

For a built-in or USB webcam, use [config.webcam.example.json](config.webcam.example.json), whose numeric `source: 0` selects the first device. It includes four **illustrative** zones for A05–A08. Edit each polygon for your own camera view. Coordinates are normalized from 0 to 1, with (0, 0) at the upper left. Remove zones that do not exist in the scene. For A07, draw the wall zone around the climbable structure and set `crossing_line_y` to the normalized vertical position of its top edge; omit the field to use upward motion alone. The optional line is horizontal and must pass through the zone. For A08, draw a **small polygon around the handle or lock**, no more than 12% of the frame. A broad door polygon cannot produce a video A08 alert. The motion estimator compares that polygon with surrounding pixels and suppresses large scene changes; `activity_threshold`, `min_activity_samples`, and `dwell_seconds` control the alert. Video A08 events have null `track_id` and `kind` because hand-only motion cannot be attributed to a detected person. The `confidence` field is a motion score, not a probability of tampering. These rules do not identify physical climbing or damage reliably.

To replace the webcam with CCTV later, copy the config to the ignored `config.local.json`, change only `source` from `0` to the camera's RTSP URL, set `SENTINEL_CONFIG=config.local.json`, and recalibrate the polygons for that camera view. Multiple camera entries can mix webcam indices and RTSP URLs; each gets its own capture, detector, tracker, and motion state. The domain rules and API do not depend on the capture source. The default detector reads `models/object_detection_yolox_2022nov.onnx`; `SENTINEL_ONNX_MODEL` overrides its location. An existing COCO YOLOv8-style ONNX model can still be used with `SENTINEL_DETECTOR=yolov8`, subject to its own license. Keep camera URLs with credentials and model files out of source control. Run on a private network and use a TLS reverse proxy before any remote use.

To check the local webcam path without storing any images, set `SENTINEL_API_KEY` and run `python scripts/check_webcam.py` after installing the dependencies and model. It starts the capture worker in process, waits for an authenticated JPEG snapshot **and one completed detector observation**, reports the detector and detection count, then stops the worker. A count of zero means the model ran but found no person or vehicle in that frame.

## API

All `/api/v1` endpoints require `X-API-Key`. Camera sources are intentionally absent from responses.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/session` | Validate an API key for console sign-in |
| GET | `/api/v1/summary` | Dashboard counts and current overview |
| GET | `/api/v1/cameras` | Camera IDs, names, source type, and zones |
| POST | `/api/v1/cameras` | Create and persist a camera |
| PUT | `/api/v1/cameras/{id}` | Update a camera name or source |
| DELETE | `/api/v1/cameras/{id}` | Stop and delete a camera configuration |
| PUT | `/api/v1/cameras/{id}/zones` | Replace and save a camera's calibrated zones |
| POST | `/api/v1/cameras/{id}/start` | Open camera and start detection |
| POST | `/api/v1/cameras/{id}/stop` | Stop worker and release camera |
| GET | `/api/v1/cameras/{id}/status` | State, detector, and current counts |
| GET | `/api/v1/cameras/{id}/tracks` | Latest person and vehicle tracks |
| POST | `/api/v1/cameras/{id}/observations` | Ingest virtual or external detector output |
| GET | `/api/v1/detections` | Recent new person/vehicle tracks |
| GET | `/api/v1/events` | Recent alerts, optionally filtered by `camera_id` |
| GET | `/api/v1/cameras/{id}/snapshot` | Latest JPEG frame |
| GET | `/api/v1/cameras/{id}/stream` | MJPEG stream |
| POST | `/api/v1/algorithm-tests` | Queue raw image/video bytes; requires `X-Filename` |
| GET | `/api/v1/algorithm-tests` | List locally stored test jobs |
| GET | `/api/v1/algorithm-tests/{id}` | Read test status and detection summary |
| GET | `/api/v1/algorithm-tests/{id}/result` | Download the authenticated annotated result |

Example observation (coordinates are normalized 0–1):

```json
{"at": 1790000000, "detections": [{"kind": "person", "box": [0.2, 0.3, 0.3, 0.7], "confidence": 0.95, "activity": 0.0}]}
```

```powershell
curl.exe -H "X-API-Key: $env:SENTINEL_API_KEY" http://127.0.0.1:8000/api/v1/cameras
```

`at` is Unix time in seconds. Omit it for server time. For virtual testing, provide increasing timestamps per camera. The most recent 1,000 alerts survive restart through the local JSON state adapter. Camera configurations load at startup. This prototype has one shared API key and no per-user, per-role, or per-site access control; those must be added before a real township deployment.

Behavior-rule migration note: A07 requires at least two upward observations and the configured total rise (`min_vertical_travel`, default `0.12`); the optional `crossing_line_y` further requires a crossing. Video A08 now uses a small door-handle zone and can emit events with null `track_id` and `kind`. External callers of `/observations` can still send person activity sequences under the previous contract. Zone updates reset current tracks and motion state for that camera. The API paths and observation fields remain unchanged.

## Architecture and testing

`domain.py` defines normalized detections, zones, tracks, and events. `analysis.py` owns rules, `tracking.py` owns track association, `service.py` owns live state behind an event-store port, `storage.py` supplies atomic JSON adapters, `video.py` adapts OpenCV and the pinned OpenCV Zoo model, `algorithm_test.py` owns bounded background media evaluation, and `api.py` exposes the contracts and routed console. Camera readers and future durable stores can be replaced without changing rules. No device is required for the automated tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

The current tracker is a simple centroid matcher. Occlusion, crossing tracks, moving cameras, and perspective changes can cause ID switches or false alerts. Test each real scene, calibrate polygons and dwell time, and replace the tracker or detectors through the existing boundaries if accuracy requires it. JSON persistence is appropriate for this single-process local prototype, but not concurrent multi-process deployment; a transactional durable store, tenant-aware authorization, model validation, and operational metrics remain production work.

The automated tests use deterministic detections and generated frames. They verify wiring and rule behavior, not climbing or tampering accuracy. The local webcam smoke check verifies that capture, JPEG delivery, and one inference pass run; it does not measure recognition quality. A07 and A08 need labeled normal and abnormal footage from the deployment view before their precision and recall can be measured. Until then, treat their alerts as prompts for human review.

The behavior-signal reuse and model decision is recorded in [ADR 001](docs/adr-001-webcam-behavior-signals.md). The routed console and JSON-state decision is recorded in [ADR 002](docs/adr-002-local-console-and-json-state.md). No new package dependency was added; provenance and the local map implementation note remain in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
