# Third-party components

- [FastAPI](https://github.com/fastapi/fastapi): MIT license; HTTP API and generated OpenAPI documentation.
- [Uvicorn](https://github.com/Kludex/uvicorn): BSD 3-Clause license; ASGI server.
- [OpenCV](https://opencv.org/license/): Apache 2.0 for versions 4.5.0 and newer; optional video capture, JPEG encoding, and media decoding.
- [NumPy](https://github.com/numpy/numpy): main project BSD 3-Clause license; image arrays. Binary wheels may contain separately licensed components; inspect the installed wheel's license file.
- [PyAV 16.1.0](https://github.com/PyAV-Org/PyAV/tree/v16.1.0): BSD-3-Clause, unmodified optional dependency for VP8/WebM previews. The inspected Windows CPython 3.14 wheel bundles shared FFmpeg libraries; its libavcodec reports LGPL version 3 or later. Keep the library replaceable and retain applicable notices and corresponding library source when redistributing; other platform wheels need their own bundled-license review. PyAV's BSD license does not replace the bundled libraries' terms. No upstream code is copied into the adapter. This is a compatibility and license inspection, not a comprehensive vulnerability audit.

Verify model-weight provenance separately from runtime package licenses when adopting a future adapter.

## Three.js 0.180.0 (r180)

The residential map uses [Three.js](https://github.com/mrdoob/three.js/tree/r180), MIT licensed, including its OrbitControls. Unmodified distribution files are bundled in `src/sentinel/web/vendor/` for offline operation. Copyright and license are retained in `THREE-LICENSE.txt`. Files were obtained from the pinned `https://cdn.jsdelivr.net/npm/three@0.180.0/` package, with no install scripts or transitive packages executed. This is not a comprehensive security audit. Update all engine/control files together when upgrading and repeat WebGL interaction checks.

SHA-256 inventory:

| File | SHA-256 |
|---|---|
| OrbitControls.js | b97879c748170baadeb3fb84cea1ffdf4674e283dc06042f34e2acb95a76042c |
| three.core.min.js | 61ba0df005b05991361d040d8ff670e1aadfd0ce7aeebd1fdb0725957a8957de |
| three.module.min.js | e2b5ee6bccd38fd6d8a2428546b83c5f2426d84b152ef82be8055556e3b40eb6 |
| THREE-LICENSE.txt | bfe119ea4fd413f5f7ca3fcd63adb0c4a073ed39daa2fe7d3e6b769e21272601 |

Geometry and procedural surface/foliage textures are project-authored interpretations of the owner-supplied layout. No external model, photograph, or texture asset is bundled, and no site data is sent to an external map service.

## Local visual analysis

- [SmolVLM2-500M-Video-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct): Apache-2.0 checkpoint, revision `db3405a20a36b388e11e70afe17484666b8f3e1a`. Downloaded separately; model card retained locally. No training dataset is downloaded or redistributed. Dataset licenses do not follow automatically from the checkpoint license.
- [Transformers 4.57.6](https://github.com/huggingface/transformers/blob/v4.57.6/LICENSE): Apache-2.0; processor and inference integration, used as an unmodified dependency.
- [PyTorch 2.10.0](https://github.com/pytorch/pytorch/blob/v2.10.0/LICENSE): BSD-style license with bundled third-party notices; CUDA wheels additionally contain NVIDIA components subject to their bundled terms.
- [torchvision 0.25.0](https://github.com/pytorch/vision/blob/v0.25.0/LICENSE): BSD-3-Clause; image/video preprocessing.
- [num2words 0.5.14](https://github.com/savoirfairelinux/num2words/blob/v0.5.14/COPYING): LGPL-2.1; required by the upstream SmolVLM video processor. Kept as an unmodified, replaceable Python dependency. Distributors must retain its license/notices and provide the applicable library source and replacement rights; it is not copied into first-party code.

Transitive dependency licenses remain in installed distribution metadata (including Hugging Face Hub, tokenizers, safetensors, Pillow, and NumPy). No remote model code is enabled. Direct inference dependencies and the checkpoint revision are pinned; this is not a full supply-chain security audit.

## Retired YOLOX integration

The prior OpenCV Zoo YOLOX adapter and downloader were removed in the SmolVLM2 migration. Historical ADRs refer to that implementation; YOLOX is not loaded by the application. Its former upstream was OpenCV Zoo commit `47534e27c9851bb1128ccc0102f1145e27f23f98`, licensed Apache-2.0.
