"""Recorded-media analysis using a bounded sequence of frames per model call."""
from __future__ import annotations

from threading import Event
from time import monotonic

from .vision import ANALYSIS_WINDOW_FRAMES, SAMPLE_INTERVAL_SECONDS, ModelBusy, VisionAnalyzer, sample_frame


class VisionSession:
    def __init__(self, analyzer: VisionAnalyzer, stop: Event | None = None, settings=None, on_finding=None,
                 save_evidence=None) -> None:
        self.save_evidence = save_evidence
        self.on_finding = on_finding
        self.sample_interval = 1 / settings.sample_fps if settings else SAMPLE_INTERVAL_SECONDS
        self.window_frames = settings.window_frames if settings else ANALYSIS_WINDOW_FRAMES
        self.analyzer = analyzer
        self.stop = stop or Event()
        self.pending = []
        self.findings: list[dict] = []
        self.next_sample = 0.0
        # Retain empty legacy fields for clients reading historical media jobs.
        self.events: list = []
        self.events_truncated = False
        self.peak: dict = {}

    def process(self, frame, at: float, detect: bool = True, activity: bool = False) -> None:
        if at + 1e-9 < self.next_sample:
            return
        self.pending.append(sample_frame(frame, at))
        self.next_sample = at + self.sample_interval
        if len(self.pending) == self.window_frames:
            self.flush()

    def flush(self) -> None:
        if not self.pending:
            return
        deadline = monotonic() + 120
        while not self.stop.is_set():
            try:
                finding = self.analyzer.analyze(tuple(self.pending))
                item = finding.public()
                if self.on_finding:
                    self.on_finding(item)
                if self.save_evidence:
                    item["evidence_frames"] = self.save_evidence(len(self.findings), tuple(self.pending))
                self.findings.append(item)
                self.pending.clear()
                return
            except ModelBusy:
                if monotonic() >= deadline:
                    raise RuntimeError("model remained busy for 120 seconds; retry this media job")
                self.stop.wait(0.2)
        raise RuntimeError("analysis cancelled")

    def draw(self, frame, at: float) -> None:
        # Preserve the source image; findings are displayed in the review timeline.
        pass
