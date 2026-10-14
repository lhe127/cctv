# ADR 005: Local SmolVLM2 visual analysis

## Decision

The owner selected HuggingFaceTB/SmolVLM2-500M-Video-Instruct as the sole active model because of local hardware constraints, and requested removal of unsupported alerts. Replace the YOLOX runtime with the official Hugging Face Transformers adapter. Keep OpenCV capture, bounded background jobs, authenticated FastAPI routes, and atomic local JSON persistence.

`VisionAnalyzer.analyze(tuple[SampledFrame, ...]) -> VisualFinding` is the replacement boundary. Samples contain JPEG bytes and offsets; results contain text, sample timing, model provenance, and `review_required=true`. Runtime tensors, processors, and hardware configuration stay inside `SmolVLM2Analyzer`. A future model such as the owner's proposed MOSS-VL needs its own adapter and evaluation, without changing camera or media-job callers. Merely pointing the SmolVLM2 adapter at unrelated weights is not supported.

## Alternatives and reuse

- Keep YOLOX for tracking plus VLM descriptions: preserves spatial rules, but the owner explicitly requested a single SmolVLM2 model.
- Wrap Transformers locally (selected): official support, Apache-2.0 library and checkpoint, compatible with CPU and CUDA, no remote inference service.
- A separate inference server adds operational overhead for the current single-process prototype. The port permits that adapter later.

Use pinned Transformers 4.57.6, PyTorch 2.10.0, torchvision 0.25.0, and num2words 0.5.14. See THIRD_PARTY_NOTICES.md for upstreams and licenses. The checkpoint is pinned by commit; no remote custom code is enabled. Downloads happen through an explicit setup script; runtime loading is local-only.

## Behavior and limits

One lazy model instance is shared by all cameras and recorded-media jobs. Inference is serialized. Capture and preview remain independent. Live sources sample one frame every 0.5 seconds, keep at most eight JPEG samples of maximum edge 512 pixels, and analyze batches of eight. This action-focused window spans 3.5 seconds; the prompt asks for observable movement/contact, ordinary activities, and uncertainty rather than appearance. Denser sampling increases compute and does not guarantee recognition accuracy. Busy live windows may be dropped. File EOF flushes a partial window. Uploaded clips are bounded to 60 seconds, with the same sample rate and window size; partial final windows are included. Multiple sampled frames use the native SmolVLM2 video processor with explicit timestamps, no further frame sampling, and 512-pixel letterboxing; a single frame uses the image processor. Audio is not analyzed.

Generation is deterministic and limited to 96 new tokens, with repeated four-token sequences suppressed. CUDA uses float16 and CPU uses float32. Maximum token and frame limits bound inference work, but native model execution cannot be forcibly interrupted by a thread; camera stop reports failure if a worker remains active beyond its join timeout. The application must run as one process to avoid duplicate GPU models and concurrent JSON writers.

### Action-window validation (2026-10-14)

Ran the updated local model on the owner's approximately 12.5-second fighting clip. Two eight-frame windows described a physical altercation, including punching or pushing, compared with the previously reported appearance-only description. Another window invented a gun and an axe, unsupported by the sampled frames inspected; the final single-frame window also misdescribed the scene. This is a limited qualitative check, not a fighting-detection benchmark. Findings remain review-required, with no automatic alerts or invented confidence scores. The increased compute and hallucinations remain limitations of this configuration; prompt wording does not guarantee uncertainty calibration. Previously stored findings are unchanged; rerun media analysis to obtain new descriptions.

Descriptions are experimental review findings. No generated score is presented as calibrated confidence. There are no active tracking boxes, exact counts, polygon/dwell alerts, or specialized fight/fall/fire/drowning classifiers. Historical event data and legacy domain types remain readable; stored camera polygons are retained for rollback but ignored by this pipeline. Existing manual observation ingestion returns HTTP 410 so it cannot secretly reactivate retired alerts.

## API and persistence

`POST /api/v1/analysis-jobs` accepts raw media bytes with `X-Filename`, returns HTTP 202 and a job ID. `GET /api/v1/analysis-jobs/{id}` returns status and findings. The existing `/algorithm-tests` routes remain aliases for media-client compatibility. `GET /api/v1/findings?camera_id=...` returns at most the last 1,000 persisted live findings. All routes require `X-API-Key`; source credentials are absent. Camera offsets are seconds since the current capture connection (or file media time), and `observed_at` is UTC completion time.

The JSON state format gains an optional `findings` array without changing its version. Old event and job records are preserved. Findings use the same retention bound as historical alerts; media-result file cleanup remains an operator retention task. Local model input samples are held in memory. Media uploads are removed after processing, and preview outputs and findings remain in the ignored data directory.

Rollback: restore the previous application revision and its former model dependency; data files remain backward readable because older storage ignores the additive findings key. New media jobs include `mode=visual_analysis`, empty legacy detection/event arrays, and a new findings array.

## Validation

Tests exercise injected model fixtures, sampling boundaries, final-window flush, preview independence, disabled legacy alerts, authenticated API jobs, persistence, and cancellation. Real model execution is tested separately; fixture tests do not establish recognition accuracy.

2026-10-14 verification: 38 automated tests passed in the owner's existing Python 3.14 venv; JavaScript syntax and generated OpenAPI schemas passed, and `pip check` reported no broken requirements. CUDA PyTorch 2.10.0 recognized the RTX 4050 Laptop GPU (6 GB). Generated image/video uploads and camera-file playback completed through the authenticated API with the real pinned checkpoint. The final smoke run took 22.63 seconds for the first image including model initialization, 3.47 seconds for a three-frame sampled video job, and 8.53 seconds for paced camera-file playback plus analysis. Peak PyTorch allocated GPU memory was 1,079 MiB; this excludes other GPU allocations and is not a capacity benchmark. The model misdescribed the synthetic moving square as a flag, illustrating why findings are not automatic safety triggers. Browser automation had no available browser, so visual UI verification remains unperformed.
