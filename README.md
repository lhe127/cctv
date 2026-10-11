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

Download the pinned Apache-2.0 model with `scripts/download_yolox.py` before starting real-video detection. Model bytes are excluded from source control. A07/A08 are review signals, not reliable behavior classifiers. A08 can still mistake ordinary handle use for suspicious activity. Alerts must be checked by a human before action.

## Run locally

Install Python 3.11+ and dependencies in your normal environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[video,test]'
.\.venv\Scripts\python.exe scripts/download_yolox.py
$env:SENTINEL_API_KEY='replace-with-a-long-local-secret'
$env:SENTINEL_CONFIG='config.webcam.example.json'
.\.venv\Scripts\python.exe -m sentinel.api
```

Open `http://127.0.0.1:8000/`, enter the same API key, click **Connect**, then **Start camera + detection**. The dashboard displays the camera frame, current person/vehicle boxes and confidence, current counts, a list of recent successful detections, and separate safety alerts. Click **Stop camera** to release the webcam. The server does not open the camera until Start is clicked. API documentation is at `/docs`.

To calibrate A05–A08, expand **Edit zones** under the running camera. Select an existing rule or **New zone**, choose its rule, click **Draw**, mark at least three corners on the video, and click **Save**. **Remove** deletes a zone. The authenticated API updates the running camera immediately and writes `config.local.json` when the server was started from an example config. On the next server start, set `SENTINEL_CONFIG=config.local.json` so the saved zones load. Editing an explicitly named private config writes back to that file. Editing zones resets current tracks for that camera; it does not erase prior alerts. Thresholds remain editable in the saved JSON.

The preview refreshes independently of inference, at up to about seven images per second in the browser. The capture worker retains only the newest frame for detection, so slow CPU inference does not build a backlog. Detection boxes can trail a moving subject because the model updates more slowly than the preview; CPU speed and model choice determine detection latency.

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
| GET | `/api/v1/cameras` | Camera IDs, names, source type, and zones |
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

Example observation (coordinates are normalized 0–1):

```json
{"at": 1790000000, "detections": [{"kind": "person", "box": [0.2, 0.3, 0.3, 0.7], "confidence": 0.95, "activity": 0.0}]}
```

```powershell
curl.exe -H "X-API-Key: $env:SENTINEL_API_KEY" http://127.0.0.1:8000/api/v1/cameras
```

`at` is Unix time in seconds. Omit it for server time. For virtual testing, provide increasing timestamps per camera. Alerts are held only in memory (most recent 1,000) and vanish on restart. Camera configurations load at startup. This prototype has one shared API key and no per-user or per-site access control; those must be added before a real township deployment.

Behavior-rule migration note: A07 requires at least two upward observations and the configured total rise (`min_vertical_travel`, default `0.12`); the optional `crossing_line_y` further requires a crossing. Video A08 now uses a small door-handle zone and can emit events with null `track_id` and `kind`. External callers of `/observations` can still send person activity sequences under the previous contract. Zone updates reset current tracks and motion state for that camera. The API paths and observation fields remain unchanged.

## Architecture and testing

`domain.py` defines normalized detections, zones, tracks, and events. `analysis.py` owns rules, `tracking.py` owns track association, `service.py` owns bounded in-memory state, `video.py` adapts OpenCV and the pinned OpenCV Zoo model, and `api.py` exposes the contracts. Camera readers can be replaced without changing rules. No device is required for the unit tests:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

The current tracker is a simple centroid matcher. Occlusion, crossing tracks, moving cameras, and perspective changes can cause ID switches or false alerts. Test each real scene, calibrate polygons and dwell time, and replace the tracker or detectors through the existing boundaries if accuracy requires it. A durable event store, tenant-aware authorization, model validation, and operational metrics are future production work.

The automated tests use deterministic detections and generated frames. They verify wiring and rule behavior, not climbing or tampering accuracy. The local webcam smoke check verifies that capture, JPEG delivery, and one inference pass run; it does not measure recognition quality. A07 and A08 need labeled normal and abnormal footage from the deployment view before their precision and recall can be measured. Until then, treat their alerts as prompts for human review.

The behavior-signal reuse and model decision is recorded in [ADR 001](docs/adr-001-webcam-behavior-signals.md). No new third-party dependency was added for these rules; existing component provenance remains in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
