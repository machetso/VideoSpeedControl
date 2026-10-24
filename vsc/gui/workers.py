"""Background work (ffprobe, frame scans, encoder detection) – never on the UI thread.

Each task runs in the global QThreadPool and reports back through Qt signals, which are
delivered to the receiving widgets on the UI thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from ..core import encoders, preview, rife
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
    done = Signal(object, object)      # dict[str, EncoderStatus], rife.RifeStatus
    failed = Signal(str)


class EncoderDetector(QRunnable):
    def __init__(self, signals: EncoderSignals, use_cache: bool = True):
        super().__init__()
        self.signals = signals
        self.use_cache = use_cache

    def run(self) -> None:
        try:
            _emit(self.signals.done, encoders.detect(self.use_cache), rife.detect())
        except Exception as e:  # noqa: BLE001
            _emit(self.signals.failed, str(e))


class FrameSignals(QObject):
    frame = Signal(object, int, object)     # path, frame index, QImage
    failed = Signal(object, int, str)


class FrameGrabber(QRunnable):
    """Decode one frame exactly (preview at the playhead)."""

    def __init__(self, clip, index: int, size: tuple[int, int], signals: "FrameSignals"):
        super().__init__()
        self.clip, self.index, self.size, self.signals = clip, index, size, signals

    def run(self) -> None:
        try:
            data = preview.grab_frame(self.clip.info, self.clip.frames, self.index, self.size)
            _emit(self.signals.frame, self.clip.path, self.index, QImage.fromData(data, "BMP"))
        except Exception as e:  # noqa: BLE001
            _emit(self.signals.failed, self.clip.path, self.index, str(e))


class FrameFetcher(QObject):
    """Decodes frames for one view: one decode at a time, and only the latest request counts.

    `source` is anything with .path, .info and .frames (a Clip or a TestMedia).
    """
    ready = Signal(object)     # QImage
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = FrameSignals(self)
        self.signals.frame.connect(self._done)
        self.signals.failed.connect(self._failed)
        self._busy = False
        self._wanted = None    # (source, index, size)
        self._running = None
        self.shown = None      # key of the image last delivered

    @staticmethod
    def _key(request):
        return None if request is None else (request[0].path, request[1], request[2])

    def request(self, source, index: int, size: tuple[int, int]) -> None:
        self._wanted = (source, index, size)
        self._next()

    def reset(self) -> None:
        self._wanted = None
        self.shown = None

    def _next(self) -> None:
        if self._busy or self._wanted is None or self._key(self._wanted) == self.shown:
            return
        self._busy, self._running = True, self._wanted
        source, index, size = self._running
        start(FrameGrabber(source, index, size, self.signals))

    def _finish(self) -> bool:
        """True if the finished decode is still the one wanted."""
        self._busy = False
        current = self._key(self._running) == self._key(self._wanted)
        if current:
            self.shown = self._key(self._running)
        return current

    def _done(self, path, index, image) -> None:
        if self._finish():
            self.ready.emit(image)
        self._next()

    def _failed(self, path, index, message) -> None:
        if self._finish():
            self.failed.emit(message)
        self._next()


@dataclass
class TestMedia:
    """The test encode's output file, readable like a clip."""
    path: Path
    info: object
    frames: object


class TestSignals(QObject):
    progress = Signal(object, object)          # clip, Progress
    done = Signal(object, object, object)      # clip, TestResult, TestMedia | None


class TestEncodeTask(QRunnable):
    def __init__(self, clip, test, signals: TestSignals):
        super().__init__()
        self.clip, self.test, self.signals = clip, test, signals

    def run(self) -> None:
        result = self.test.run(lambda p: _emit(self.signals.progress, self.clip, p))
        media = None
        if result.ok:
            try:
                info = probe(result.output)
                media = TestMedia(result.output, info, scan_frames(result.output, info.stream_index))
            except Exception:  # noqa: BLE001 – comparison is optional (e.g. image sequences)
                media = None
        _emit(self.signals.done, self.clip, result, media)


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
