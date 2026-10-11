# Third-party components

- [FastAPI](https://github.com/fastapi/fastapi): MIT license; HTTP API and generated OpenAPI documentation.
- [Uvicorn](https://github.com/Kludex/uvicorn): BSD 3-Clause license; ASGI server.
- [OpenCV](https://opencv.org/license/): Apache 2.0 for versions 4.5.0 and newer; optional video capture, JPEG encoding, and ONNX inference.
- [NumPy](https://github.com/numpy/numpy): main project BSD 3-Clause license; optional ONNX output handling. Binary wheels may contain separately licensed components; inspect the installed wheel's license file.

No other third-party source or model weights are copied into this repository. Verify the provenance of any replacement ONNX weights before deployment; package licenses do not establish model-weight rights.

## OpenCV Zoo YOLOX-S

The project vendors `models/object_detection_yolox/yolox.py` from [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/object_detection_yolox) at commit `47534e27c9851bb1128ccc0102f1145e27f23f98`, with only a provenance comment added. The original directory and its ONNX weights are licensed Apache 2.0; the license text is preserved in `src/sentinel/vendor/OPENCV_ZOO_YOLOX_LICENSE`.

The local model file is downloaded separately by `scripts/download_yolox.py` and is excluded from source control. Its SHA-256 is `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`. Training-data rights and deployment accuracy should be reviewed for any production use.
