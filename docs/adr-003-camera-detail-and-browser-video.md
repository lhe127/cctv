# ADR 003: Camera detail and browser-compatible results

## Decision

Keep the existing FastAPI/static-JavaScript architecture. A camera's controls,
preview, zones, behavior signals, and filtered alerts live at `/cameras/{id}`.
The authenticated `GET /api/v1/cameras/{id}` uses the existing sanitized camera
contract. Existing camera APIs and persisted JSON data remain compatible.

Reuse OpenCV's VP8 encoder for WebM algorithm results instead of MPEG-4 Part 2
in MP4. The latter is not reliably playable in browsers. Introducing a separate
FFmpeg subprocess or a streaming service would add unnecessary operational
dependencies for bounded local test clips. See the [MDN codec guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Video_codecs)
and [OpenCV VideoWriter documentation](https://docs.opencv.org/3.4.16/dd/d9e/classcv_1_1VideoWriter.html).
No copied third-party source or new dependency is introduced.

Preview encoding defaults to 5 FPS and object inference to 2 FPS. Source capture
still drains continuously into a latest-frame slot, preventing latency buildup.
The browser limits snapshot requests to one at a time and 5 FPS. Behavior tiles
represent recent emitted alerts, not a continuous action classifier; stale or
stopped cameras do not highlight them. Fire/fall require future model adapters.

## Consequences and recovery

OpenCV must include VP8 encoding support. Results omit audio, as before. Lower
inference rates trade compute cost for temporal detail and need scenario testing.
Legacy MP4 outputs convert lazily outside the API event loop, with conversion
serialized and original files preserved. Metadata switches to the WebM path;
there is no schema migration. Back up the JSON state and result directory before
deployment; restore both together if rolling back to an older application version.

Verification covers route/authentication behavior, camera alert isolation, WebM
encoding and legacy conversion, plus browser playback and simulated-camera live
preview. Real hardware and behavior accuracy need separate deployment validation.
