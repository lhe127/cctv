"""Silent VP8 preview encoding behind a small media adapter."""
from fractions import Fraction
from pathlib import Path


class WebMWriter:
    """Encode BGR frames without OpenCV's AVI FourCC/WebM tag mismatch."""

    def __init__(self, path: Path, fps: float, size: tuple[int, int]) -> None:
        import av

        self._container = av.open(str(path), mode="w", format="webm")
        self._closed = False
        try:
            self._stream = self._container.add_stream(
                "libvpx", rate=Fraction(str(fps)).limit_denominator(10000)
            )
            self._stream.width, self._stream.height = size
            self._stream.pix_fmt = "yuv420p"
            self._stream.options = {"deadline": "realtime", "cpu-used": "4"}
            self._stream.codec_context.thread_count = 2
        except Exception:
            self._container.close()
            raise

    def write(self, frame) -> None:
        import av

        if self._closed:
            raise RuntimeError("WebM writer is closed")
        for packet in self._stream.encode(av.VideoFrame.from_ndarray(frame, format="bgr24")):
            self._container.mux(packet)

    def release(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            for packet in self._stream.encode():
                self._container.mux(packet)
        finally:
            self._container.close()
