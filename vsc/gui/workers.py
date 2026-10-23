"""Background work (ffprobe, frame scans, encoder detection) – never on the UI thread.

Each task runs in the global QThreadPool and reports back through Qt signals, which are
delivered to the receiving widgets on the UI thread.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from ..core import encoders, preview
from ..core.probe import probe, scan_frames


def _emit(signal, *args) -> bool:
    """Emit unless the receiving side was deleted meanwhile (window closed)."""
    try:
        signal.emit(*args)
        return True
    except RuntimeError:
        return False


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
            _emit(self.signals.probed, self.path, info)
            frames = scan_frames(self.path, info.stream_index)
            _emit(self.signals.scanned, self.path, frames)
        except Exception as e:  # noqa: BLE001 – any failure is shown on the clip row
            _emit(self.signals.failed, self.path, str(e))


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
            _emit(self.signals.done, encoders.detect(self.use_cache))
        except Exception as e:  # noqa: BLE001
            _emit(self.signals.failed, str(e))


class FrameSignals(QObject):
    frame = Signal(object, int, object)     # path, frame index, QImage
    failed = Signal(object, int, str)


class FrameGrabber(QRunnable):
    """Decode one frame exactly (preview at the playhead)."""

    def __init__(self, clip, index: int, size: tuple[int, int], signals: FrameSignals):
        super().__init__()
        self.clip, self.index, self.size, self.signals = clip, index, size, signals

    def run(self) -> None:
        try:
            data = preview.grab_frame(self.clip.info, self.clip.frames, self.index, self.size)
            _emit(self.signals.frame, self.clip.path, self.index, QImage.fromData(data, "BMP"))
        except Exception as e:  # noqa: BLE001
            _emit(self.signals.failed, self.clip.path, self.index, str(e))


class ThumbnailSignals(QObject):
    thumbnail = Signal(object, int, int, object)   # clip, slot, frame index, QImage


THUMB_COUNT = 24
THUMB_HEIGHT = 72


class ThumbnailLoader(QRunnable):
    """Fast keyframe thumbnails for the timeline, one after another."""

    def __init__(self, clip, signals: ThumbnailSignals):
        super().__init__()
        self.clip, self.signals = clip, signals

    def run(self) -> None:
        info, frames = self.clip.info, self.clip.frames
        size = preview.fit_size(info, THUMB_HEIGHT * 4, THUMB_HEIGHT)
        for slot, index in enumerate(preview.thumbnail_frames(frames, THUMB_COUNT)):
            if self.clip.removed:
                return
            try:
                data = preview.grab_frame(info, frames, index, size, accurate=False)
            except Exception:  # noqa: BLE001 – a missing thumbnail is not worth an error
                continue
            if not _emit(self.signals.thumbnail, self.clip, slot, index,
                         QImage.fromData(data, "BMP")):
                return


def start(task: QRunnable) -> None:
    QThreadPool.globalInstance().start(task)
