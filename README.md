# Township Sentinel

Local camera preview and image/video analysis using **HuggingFaceTB/SmolVLM2-500M-Video-Instruct**. SmolVLM2 is the only active model. It returns timestamped descriptions and explicit danger flags for human review. Tracking and legacy zone-rule detection remain disabled.

## Setup in the existing virtual environment

```powershell
# NVIDIA GPU installation (the current machine has an RTX 4050)
.\.venv\Scripts\python.exe -m pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -e '.[vlm,test]'
.\.venv\Scripts\python.exe scripts/download_smolvlm.py
```

For CPU-only installation, omit the first command. The model defaults to CUDA when the installed PyTorch build detects it, otherwise CPU. The download script pins the checkpoint revision and saves it under the ignored `models/smolvlm2-500m/` folder. Inference does not download files or send media to a hosted service.

```powershell
$env:SENTINEL_API_KEY='choose-a-private-key'
$env:SENTINEL_CONFIG='config.local.json'
.\.venv\Scripts\python.exe -m sentinel.api
```

Open `http://127.0.0.1:8000/`. If you do not have a local camera config, use `config.webcam.example.json` to select webcam index 0, or create sources in Camera management. RTSP URLs and local video files remain supported. Existing cameras and saved historical events are preserved. Configured polygons are ignored by the new analysis pipeline.

## How analysis works

- Camera preview runs independently of inference, with JPEG production at 5 FPS by default.
- The analyzer samples one frame every 0.5 seconds and processes eight chronological frames per window (3.5 seconds from first to last sample), resized to a maximum edge of 512 pixels. A partial final window is analyzed at file EOF. The prompt prioritizes observable actions and interactions, including ordinary activities and possible physical contact, and asks for uncertainty when motion is unclear. This increases processing cost compared with the former four-frame, two-second sampling; live windows may be skipped while inference is busy. It does not establish fighting-detection accuracy.
- One model instance is shared across all cameras and uploads. Live windows can be skipped when the model is busy; this is sampled analysis, not continuous action detection.
- The camera page and Review findings page show descriptions, sample windows, and analysis state. The model does not provide validated boxes, persistent IDs, exact counts, or reliable safety triggers.
- The media lab accepts JPG, PNG, WEBP, MP4, MOV, AVI, and MKV, up to 100 MB. Videos are limited to the first 60 seconds, with a maximum 4K source resolution. Source previews are JPEG or silent VP8/WebM; findings appear alongside playback. Uploaded input files are deleted when jobs finish.

Model outputs can be incorrect. A description or a `no` result does not establish that a scene is safe. Explicit model danger flags now create review alerts; this is not a validated detector for particular incident types. No physical response is automated, and legacy intrusion, loitering, climbing, tampering, pool, crowd, parking, and unattended-object rule engines remain inactive.

## Configuration

An empty or malformed history file is preserved as `sentinel-state.json.corrupt-<unique-id>` beside the original, and the application starts a fresh history with a warning. Camera configuration is separate and remains unchanged. Recovery cannot reconstruct missing records; retain the preserved file if manual recovery is needed. State writes flush to disk before atomic replacement. Unsupported state versions and filesystem access errors still stop startup rather than resetting history.

### OpenCV WebM warning

WebM previews now use the PyAV adapter in `webm.py`, selecting VP8 directly rather than passing an AVI FourCC through OpenCV. This removes the `tag 0x30385056/'VP80' is not supported` warning. Both upload previews and legacy conversions use the same adapter; output stays silent VP8/WebM. Existing installations need `.\.venv\Scripts\python.exe -m pip install av==16.1.0` and a server restart. Encoder errors remain visible and fail the job. Tests decode every output frame and check that the old warning is absent.

| Variable | Default | Purpose |
|---|---|---|
| `SENTINEL_API_KEY` | Required | Shared local API key |
| `SENTINEL_CONFIG` | `data/cameras.json` | Camera configuration |
| `SENTINEL_DATA_FILE` | `data/sentinel-state.json` | Local state |
| `SENTINEL_VLM_DEVICE` | `auto` | `auto`, `cpu`, or `cuda` |
| `SENTINEL_VLM_MODEL_PATH` | `models/smolvlm2-500m` | Local copy of the pinned SmolVLM2 checkpoint |
| `SENTINEL_PREVIEW_FPS` | `5` | JPEG preview rate, 1–15 |
| `SENTINEL_PORT` | `8000` | HTTP port |
| `SENTINEL_LOG_LEVEL` | `INFO` | Log verbosity |

Restart the server after changing code or configuration. Former `SENTINEL_DETECTOR`, `SENTINEL_ONNX_MODEL`, `SENTINEL_TRACKER`, and `SENTINEL_INFERENCE_FPS` settings no longer select the production analysis pipeline. The earlier centroid/ByteTrack defaults are superseded by visual descriptions without tracking.

## API

All `/api/v1` requests require `X-API-Key`. OpenAPI is available at `/docs`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/v1/analysis-jobs` | Queue raw media bytes with `X-Filename`; returns 202 |
| GET | `/api/v1/analysis-jobs/{id}` | Status and model findings |
| GET | `/api/v1/analysis-jobs/{id}/result` | Authenticated source preview |
| GET | `/api/v1/findings` | Persisted camera findings; optional `camera_id` |
| GET | `/api/v1/capabilities` | Active model capabilities |
| GET / POST | `/api/v1/cameras` | List / create cameras |
| GET / PUT / DELETE | `/api/v1/cameras/{id}` | Inspect / update / delete camera |
| POST | `/api/v1/cameras/{id}/start` | Start capture and analysis |
| POST | `/api/v1/cameras/{id}/stop` | Stop workers |
| GET | `/api/v1/cameras/{id}/status` | Capture and analysis status |
| GET | `/api/v1/cameras/{id}/snapshot` | JPEG preview |
| GET | `/api/v1/cameras/{id}/stream` | MJPEG preview |
| GET | `/api/v1/events` | Read historical alerts |
| GET | `/api/v1/alerts?status=pending` | List model-danger alerts; optional pending/resolved filter |
| PATCH | `/api/v1/alerts/{id}` | Set `{"status":"resolved"}` or `{"status":"pending"}` |

The `/api/v1/algorithm-tests` routes remain media-job aliases, including authenticated preview downloads at `/{id}/result`. `/observations` returns 410 because object observation ingestion is retired. Stored legacy zone configuration remains editable through its existing API for compatibility but has no effect on analysis.

```powershell
curl.exe -H "X-API-Key: $env:SENTINEL_API_KEY" -H 'X-Filename: clip.mp4' -H 'Content-Type: video/mp4' --data-binary '@clip.mp4' http://127.0.0.1:8000/api/v1/analysis-jobs
```

Each finding includes `description`, `model`, `revision`, `start_seconds`, `end_seconds`, `frames_analyzed`, and `review_required: true`. Live findings additionally include `id`, `camera_id`, and UTC `observed_at` (completion time). Offsets identify the sampled window, not exact event boundaries. No invented probability is returned.

Camera status explicitly reports `tracking_supported: false`; former person/vehicle count fields are `null` rather than claiming that nobody is present.

## Architecture and verification

`vision.py` defines the model-independent contract. `smolvlm.py` implements local inference. `video.py` owns capture and live sampling; `vision_session.py` owns recorded sampling; `algorithm_test.py` owns bounded jobs. `service.py`, `storage.py`, and `api.py` own state, persistence, and transport. A future VLM requires a new `VisionAnalyzer` adapter, with no model-specific code in the dashboard. See [ADR 005](docs/adr-005-local-smolvlm2.md).

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/evaluate_clips.py path/to/clip.mp4
```

Unit and integration tests use fixtures and do not require model weights or physical cameras. The clip command uses the real model and prints descriptions; it does not certify behavior detection accuracy. Historical ADRs describe superseded implementations.

Run one API process: multiple processes duplicate model memory and cannot safely share the JSON store. Camera stop waits for the current bounded generation; it reports an error if the worker has not stopped within its timeout. Findings retain the latest 1,000 entries. Media previews remain under `data/algorithm-results/`; apply a local deletion/retention policy. The prototype uses a shared API key and lacks per-user/site authorization. Use a private network and TLS proxy for remote access.

## Map coordinates, patrol simulation, and settings

The residential WebGL map reuses bundled Three.js (MIT). Add or edit a camera in **Cameras** and enter both map coordinates: center `(0, 0)`, X from −80 to 80 (positive east/right), Y from −55 to 55 (positive north/up). These are illustrative plan units, not GPS or surveyed metres. Only positioned cameras get camera-icon pins. Legacy cameras remain unplaced. Clear both fields to remove placement. API camera POST/PUT accepts `"map_position": {"x": 12, "y": -8}`; PUT omission preserves the location and explicit `null` clears it. Positions persist with the camera configuration.

A virtual patrol robot follows the same closed perimeter curve used to draw the road, at four plan units per second. It runs while the map is visible, pauses when the tab is hidden, and resets when the page reopens. It is explicitly a **simulation**, not connected hardware, navigation planning, or a safety system.

Open **Settings** to edit the VLM prompt, sampled frames per second (0.25–10), frames per model call (1–8), output token limit (16–256), and preview FPS (1–15). Prompt/token changes take effect at the next model call. Sampling/window/preview settings are captured when a camera starts; stop/start existing cameras to apply them. Recorded jobs capture sampling settings when execution starts, including queued jobs. Model throughput is hardware-dependent; sampling FPS is not inference calls per second. Busy live windows can be dropped.

`GET` and `PUT /api/v1/settings` require `X-API-Key` and administrator authorization. Set `SENTINEL_ADMIN_API_KEY` before server startup to require a separate `X-Admin-Key` for settings (enter it on the Settings page; it is not stored in browser storage). Without it, the existing API key retains local-owner access. This is shared-key access, not a multi-user role system. Settings persist atomically in `<state-file-stem>-settings.json` beside `SENTINEL_DATA_FILE`. Invalid files fail startup rather than silently discarding settings. Persisted preview settings override `SENTINEL_PREVIEW_FPS`; that environment variable supplies the initial default. Model path/device remain environment settings requiring restart. Run only one API process against these local JSON files.

No new runtime dependencies or external map/model assets were introduced. Existing map architecture is documented in [ADR 004](docs/adr-004-architectural-map.md).

## Danger-alert lifecycle

### Analysis timeline frame evidence

Algorithm tests accept optional **Map X / Map Y** coordinates (center 0,0;
X −80…80, Y −55…55). Enter both or neither. The submitted location is saved
with the job and its pending danger alerts, so the map can display them without
creating a camera. Existing results are not relocated. The upload APIs accept
`?map_x=12&map_y=-8`; manual coordinates override the associated camera location
for this test only. Without coordinates, an API-associated camera's location is
used; otherwise alerts remain unplaced. Invalid/partial coordinates return 422.

New algorithm tests save the exact sampled JPEGs passed to the model. Each timeline
result displays timestamped thumbnails; selecting one pauses/seeks source playback.
These are all inputs for the analysis window, not a claim that the model localized
the hazard to one frame. Both local and cloud providers use this evidence path.
Older results have no saved evidence and must be rerun. Thumbnails load lazily via
authenticated `GET /api/v1/analysis-jobs/{id}/findings/{finding_index}/frames/{frame_index}`
(zero-based indices; 404 for unknown evidence, 410 for a missing file). Findings
include `evidence_frames: [{"offset_seconds": 0.0}]`. Files remain beside result
media with the same local retention policy; protect them as surveillance footage.

### Optional Qwen Cloud provider

In **Settings → Model provider**, enable **Use qwencloud VLM API**, enter the API
key, workspace ID, matching region and vision model, then save. Disabled uses local
SmolVLM; enabled sends sampled footage to Alibaba Cloud for both camera analysis
and algorithm tests. Both use your configured prompt and create pending alerts
for valid danger results. No new dependency is required. See [cloud setup,
credential storage, API contract and limitations](docs/qwen-cloud.md).

The previous fire-video formatting bug is addressed, but the real local 500M
model retest still missed the fire. Neither provider is a validated safety detector.
No live Qwen accuracy test has been performed without an authorized API key.

**Settings → VLM prompt defines the danger criteria for both cameras and algorithm tests.** The local model adapter appends only decision/evidence instructions and a required output contract: first line `DANGER: yes`, `DANGER: no`, or `DANGER: uncertain`, followed by visible evidence. It tells the model to follow the configured criteria and exclusions, without adding a separate hardcoded danger list. The default editable prompt covers visible assault, fire, falling, or distress and excludes ordinary activity; saved custom prompts are preserved. Define criteria explicitly, for example: `Treat a person visibly entering the swimming pool as danger. Walking beside the pool is not danger. If entry is unclear, report uncertain.` This is a configuration example, not a validated pool-safety detector.

Saving the shared prompt affects the next model call in both paths, including subsequent windows of a running camera or media job; completed findings are not reclassified. Only a valid explicit `yes` with nonempty evidence invokes `AlertService.record_finding`. Free-text keywords alone never trigger alerts. Findings expose `danger_status`; older findings default to `uncertain` and are not retroactively classified.

The **Use surveillance prompt** button loads broad scene-aware criteria for fire, falls, water distress, perimeter climbing, forced entry, violence and collisions; click Save settings to apply. The preset is also the default for new configurations. See the [copyable surveillance prompt](docs/surveillance-prompt.md). The authenticated/admin `GET /api/v1/settings/surveillance-prompt` endpoint returns this preset without changing settings.

The model is asked for one decision followed by an evidence sentence, rather than a list of alternative answer examples. The existing Transformers `prefix_allowed_tokens_fn` API constrains the generated header to exactly one of the three decisions followed by `EVIDENCE:`; the model still chooses the decision. Evidence remains generated, not hardcoded. This reuses the installed runtime without a new dependency ([upstream generation API](https://huggingface.co/docs/transformers/v4.43.3/en/main_classes/text_generation)). Parsing accepts whitespace/case variations and the known `ANGER:` typo. Invalid/missing/repeated/conflicting decisions get at most one repair inference using the same frames and criteria. If repair fails, the finding remains uncertain with `analysis_warning`; it is not a safe result and creates no automatic danger alert. Legitimate uncertainty is not retried to force a positive decision. Repairs may double generation cost for malformed windows. The camera/algorithm timelines display decision and warning labels; a later negative window never clears an earlier pending danger alert.

Live camera findings and uploaded-media analyses use the same alert function immediately after each analyzed window. Alerts already recorded remain available even if a later window or preview encoding fails. Every flagged analysis window creates a separate pending alert, deduplicated by finding ID; neighboring windows are not automatically merged into an incident. Uploaded media is labeled as such (an old clip is not a live event). Its alert timestamp is processing time, and offsets refer to the source clip. An upload associated with a camera uses that camera's configuration captured at submission; unassociated uploads remain unplaced.

Open **Alerts & review** to filter all/pending/resolved, mark an alert resolved, or reopen it. The API key grants these operator actions; the separate admin key remains specific to analysis settings. Status and UTC timestamps persist atomically in the existing state JSON. Retrying the same status is idempotent, and redelivery of a finding cannot reopen a resolved alert. This shared-key prototype does not identify individual resolvers or provide a full audit trail of past status transitions.

The map polls pending alerts every five seconds while visible. It groups colocated alerts into counted red pins independently of the camera-pin toggle, and lists every pending alert in its sidebar. Unplaced alerts are explicitly listed without invented coordinates. Locations and camera names are snapshots at detection/submission time, preserved after moving or deleting cameras; later coordinate edits do not relocate historical incidents. Resolving removes a marker on the next refresh, unless other pending alerts remain there. Refresh failures display a stale-data warning.

Alert history is retained separately from the bounded findings history and is not silently truncated, including unresolved alerts. Monitor state-file growth; larger deployments need a database, pagination, retention policy, and per-user authorization. No new dependencies were introduced. Automated tests and fixture-backed browser checks verify the workflow, not real-world model accuracy or reliability of format compliance. Treat all danger alerts as review requests, not verified emergencies. Restart the backend after upgrading; existing settings and legacy event history remain compatible.
