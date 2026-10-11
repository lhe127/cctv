"""Download the pinned OpenCV Zoo YOLOX-S model and verify its SHA-256."""
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

COMMIT = "47534e27c9851bb1128ccc0102f1145e27f23f98"
URL = ("https://github.com/opencv/opencv_zoo/raw/" + COMMIT
       + "/models/object_detection_yolox/object_detection_yolox_2022nov.onnx")
EXPECTED_SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
DESTINATION = Path(__file__).resolve().parents[1] / "models" / "object_detection_yolox_2022nov.onnx"


def main() -> None:
    DESTINATION.parent.mkdir(exist_ok=True)
    temporary = DESTINATION.with_suffix(".download")
    digest = sha256()
    try:
        with urlopen(URL, timeout=30) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != EXPECTED_SHA256:
            raise ValueError("model SHA-256 did not match the pinned OpenCV Zoo file")
        temporary.replace(DESTINATION)
        print(f"Verified model: {DESTINATION}")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
