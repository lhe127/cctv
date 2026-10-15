# Qwen Cloud analysis

Settings starts with **Use qwencloud VLM API** (off by default). Configure your
Alibaba Model Studio workspace ID, matching region/API key, vision model (default
`qwen3-vl-plus`) and timeout, then save. Both camera workers and algorithm tests
use the same provider selector, prompt, sampled frames and pending-alert callback.
Disabling the toggle selects local SmolVLM on the next analysis call. In-flight
calls finish with their original settings. Restart cameras after sampling changes.

Cloud input is 1–8 chronological JPEG frames with timestamps, not a camera URL or
continuous video/audio upload. This also handles short clips and final partial
windows. Small/brief hazards can be missed by sampling or by either model.
Explicit `yes` creates a pending human-review alert; malformed, truncated or
conflicting responses are uncertain. API errors are visible in camera status or
failed test jobs; there is no automatic fallback, network retry, or forced danger
classification. Busy live windows may be skipped. Cloud latency and charges apply.

## Credentials and API contract

Admin-protected `GET/PUT /api/v1/settings` includes `qwen_enabled`, `qwen_region`,
`qwen_workspace`, `qwen_model`, `qwen_timeout` (5–90 seconds). PUT additionally
accepts write-only `qwen_api_key` and `clear_qwen_api_key`. Blank/omitted keys preserve
the saved key. GET returns only `qwen_key_configured`, never the key. Do not include
this read-only indicator when sending a PUT. Enabling without key/workspace is 422.

Keys entered in the UI are stored **unencrypted on the server** in the existing
`<state-stem>-settings.json` (normally git-ignored `data/`). Restrict file access and
backup access to the server account. Prefer the `DASHSCOPE_API_KEY` environment
variable to keep credentials out of this file. A saved key takes precedence;
clearing it does not remove an environment key. Use HTTPS if exposing the app
beyond localhost. The browser does not persist or receive the saved Qwen key.

Only fixed Alibaba regional HTTPS hosts are used; workspace IDs cannot contain
URL separators. Redirects are rejected. Provider error bodies are not exposed.
Turning cloud on authorizes transmission of sampled footage; assess privacy,
consent, retention and regional processing requirements before enabling it.

## Reuse / design decision

Reuse the existing VisionAnalyzer/frame sampler, settings store and AlertService.
Use Python's standard-library HTTPS client behind `QwenAnalyzer`, avoiding a new
SDK/dependency for one bounded endpoint. Shared output parsing is independent of
both adapters. No third-party source or model assets were copied or installed.

Protocol and model support were checked against the official
[Alibaba visual understanding documentation](https://www.alibabacloud.com/help/en/model-studio/vision).
The endpoint is `https://<workspace>.<region>.maas.aliyuncs.com/compatible-mode/v1/chat/completions`.
Model availability depends on the account/region. Cloud model revisions are not
pinned (`cloud-unpinned` in findings). Offline fixture tests validate wiring, not
detection accuracy. Live cloud accuracy must be evaluated with authorized footage
and a configured account before operational use.

## Local fire-video limitation

The surveillance preset includes building fires even when no person is visible,
falls, possible drowning, climbing, forced entry and other visible hazards. The
response parser now handles `ANGER: yes` and refuses contradictory decisions;
local generation constrains decision syntax and retries malformed output once.
However, a real retest of the supplied fire clip still produced a false negative
with the local 500M SmolVLM model. This is **not** resolved by output formatting.
Do not interpret “no danger” as a safety guarantee or use this as the sole alarm.

Rollback: disable cloud and restart the app with local weights installed. No alert
schema migration is required. Older application versions may reject the new
settings fields: back up settings, then remove only the `qwen_*` fields before
running an older version. Preserve prompts and sampling values.
