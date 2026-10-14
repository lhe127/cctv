# Third-party components

- [FastAPI](https://github.com/fastapi/fastapi): MIT license; HTTP API and generated OpenAPI documentation.
- [Uvicorn](https://github.com/Kludex/uvicorn): BSD 3-Clause license; ASGI server.
- [OpenCV](https://opencv.org/license/): Apache 2.0 for versions 4.5.0 and newer; optional video capture, JPEG encoding, and ONNX inference.
- [NumPy](https://github.com/numpy/numpy): main project BSD 3-Clause license; optional ONNX output handling. Binary wheels may contain separately licensed components; inspect the installed wheel's license file.

Verify the provenance of any replacement ONNX weights before deployment; package licenses do not establish model-weight rights.

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

## OpenCV Zoo YOLOX-S

The project vendors `models/object_detection_yolox/yolox.py` from [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/object_detection_yolox) at commit `47534e27c9851bb1128ccc0102f1145e27f23f98`, with only a provenance comment added. The original directory and its ONNX weights are licensed Apache 2.0; the license text is preserved in `src/sentinel/vendor/OPENCV_ZOO_YOLOX_LICENSE`.

The local model file is downloaded separately by `scripts/download_yolox.py` and is excluded from source control. Its SHA-256 is `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`. Training-data rights and deployment accuracy should be reviewed for any production use.
