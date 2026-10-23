"""Background work (ffprobe, frame scans, encoder detection) – never on the UI thread.

Each task runs in the global QThreadPool and reports back through Qt signals, which are
delivered to the receiving widgets on the UI thread.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core import encoders
from ..core.probe import probe, scan_frames


class ClipSignals(QObject):
    probed = Signal(object, object)    # path, MediaInfo
    scanned = Signal(object, object)   # path, FrameMap
    failed = Signal(object, str)       # path, message


class ClipLoader(QRunnable):
    """Probe a file (fast), then scan its packets for exact frame times and keyframes."""

    def __init__(self, path: Path, signals: ClipSignals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self) -> None:
        try:
            info = probe(self.path)
            self.signals.probed.emit(self.path, info)
            frames = scan_frames(self.path, info.stream_index)
            self.signals.scanned.emit(self.path, frames)
        except Exception as e:  # noqa: BLE001 – any failure is shown on the clip row
            self.signals.failed.emit(self.path, str(e))


class EncoderSignals(QObject):
    done = Signal(object)              # dict[str, EncoderStatus]
    failed = Signal(str)


class EncoderDetector(QRunnable):
    def __init__(self, signals: EncoderSignals, use_cache: bool = True):
        super().__init__()
        self.signals = signals
        self.use_cache = use_cache

    def run(self) -> None:
        try:
            self.signals.done.emit(encoders.detect(self.use_cache))
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(str(e))


def start(task: QRunnable) -> None:
    QThreadPool.globalInstance().start(task)
