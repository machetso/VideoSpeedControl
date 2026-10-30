# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Background work (ffprobe, frame scans, encoder detection) – never on the UI thread.

Each task runs in the global QThreadPool and reports back through Qt signals, which are
delivered to the receiving widgets on the UI thread.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from ..core import encoders, ffmpeg_bin, playback, preview, preview_cache, rife, smart, treatment
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
    identified = Signal(object, str)   # path, content fingerprint (finds its stored preview)
    scanned = Signal(object, object)   # path, FrameMap
    analysed = Signal(object, object)  # path, safe join keyframes for smart re-encode (list)
    failed = Signal(object, str)       # path, message


class ClipLoader(QRunnable):
    """Probe a file (fast), then scan its packets for exact frame times and keyframes."""

    def __init__(self, path: Path, signals: ClipSignals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self) -> None:
        cache = preview_cache.PreviewCache()
        try:
            info = probe(self.path)
            _emit(self.signals.probed, self.path, info)
            try:
                fp = treatment.fingerprint(self.path)
                _emit(self.signals.identified, self.path, fp)
            except OSError:
                fp = None
            frames = cache.load_frames(fp) if fp else None          # stored preview (0.93)
            if frames is None:
                frames = scan_frames(self.path, info.stream_index)
                if fp:
                    try:
                        cache.save_frames(fp, frames)
                    except OSError:
                        pass
            _emit(self.signals.scanned, self.path, frames)
        except Exception as e:  # noqa: BLE001 – any failure is shown on the clip row
            _emit(self.signals.failed, self.path, str(e))
            return
        if smart.unavailable_reason(info) is None:
            try:     # reads the whole bitstream – after the clip is usable
                joins = cache.load_joins(fp, frames.count) if fp else None
                if joins is None:
                    joins = smart.join_points(self.path, info, frames)
                    if fp:
                        try:
                            cache.save_joins(fp, frames.count, joins)
                        except OSError:
                            pass
                _emit(self.signals.analysed, self.path, joins)
            except Exception:  # noqa: BLE001 – smart re-encode just stays unavailable
                _emit(self.signals.analysed, self.path, [])


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

    def supersede(self) -> None:
        """Another picture is on screen now: drop the pending request, deliver again later."""
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
                path = result.preview or result.output     # AV2: decoded copy
                info = probe(path)
                media = TestMedia(path, info, scan_frames(path, info.stream_index))
            except Exception:  # noqa: BLE001 – comparison is optional (e.g. image sequences)
                media = None
        _emit(self.signals.done, self.clip, result, media)


class BatchSignals(QObject):
    started = Signal(int)                  # item index
    progress = Signal(int, object)         # item index, runner.Progress
    item_done = Signal(object)             # batch.ItemResult
    finished = Signal(object)              # batch.BatchResult


class BatchTask(QRunnable):
    """Runs a whole export batch, one clip after another."""

    def __init__(self, job_batch, signals: BatchSignals):
        super().__init__()
        self.batch, self.signals = job_batch, signals

    def run(self) -> None:
        result = self.batch.run(lambda i: _emit(self.signals.started, i),
                                lambda i, p: _emit(self.signals.progress, i, p),
                                lambda r: _emit(self.signals.item_done, r))
        _emit(self.signals.finished, result)


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
        fp = getattr(self.clip, "fingerprint", None)
        cache = preview_cache.PreviewCache()
        stored = cache.load_thumbs(fp, frames.count) if fp else None     # stored preview (0.93)
        if stored is not None and len(stored) == THUMB_COUNT:
            for slot, (index, data) in enumerate(stored):
                if not data:
                    continue
                if not _emit(self.signals.thumbnail, self.clip, slot, index, QImage.fromData(data, "BMP")):
                    return
            return
        size = preview.fit_size(info, THUMB_HEIGHT * 4, THUMB_HEIGHT)
        made = []
        for slot, index in enumerate(preview.thumbnail_frames(frames, THUMB_COUNT)):
            if self.clip.removed:
                return
            try:
                data = preview.grab_frame(info, frames, index, size, accurate=False)
            except Exception:  # noqa: BLE001 – a missing thumbnail is not worth an error
                made.append((index, b""))
                continue
            made.append((index, data))
            if not _emit(self.signals.thumbnail, self.clip, slot, index,
                         QImage.fromData(data, "BMP")):
                return
        if fp:
            try:
                cache.save_thumbs(fp, frames.count, made)
            except OSError:
                pass


class ProxySignals(QObject):
    progress = Signal(object)        # clip (more of its preview copy is ready)


_proxy_lock = threading.Lock()       # one preview copy at a time – they are CPU heavy


class ProxyLoader(QRunnable):
    """Small JPEG copy of every frame (clip.proxy), so scrubbing shows pictures at once.

    Stored previews (0.93): chunks kept in the cache are loaded, only the missing ones are
    decoded (from their keyframe) and each is stored as soon as it is complete.
    """

    def __init__(self, clip, signals: ProxySignals):
        super().__init__()
        self.clip, self.signals = clip, signals

    def run(self) -> None:
        with _proxy_lock:
            clip = self.clip
            if clip.removed:
                return
            frames = clip.frames
            step = preview.proxy_step(frames)
            clip.proxy_step = step
            clip.proxy = [None] * -(-frames.count // step)
            w, h = preview.fit_size(clip.info, *preview.PROXY_SIZE)
            fp = getattr(clip, "fingerprint", None)
            cache = preview_cache.PreviewCache() if fp else None
            parts = preview_cache.chunks(frames)
            header = lambda a, b: (preview_cache.VERSION, frames.count, w, h, step, a, b,  # noqa: E731
                                   preview.PROXY_QUALITY)
            wanted = {a: [f for f in range(a, b) if f % step == 0] for a, b in parts}
            missing = []
            for a, b in parts:
                entries = cache.load_chunk(fp, header(a, b), a) if cache else None
                if entries is not None and [f for f, _ in entries] == wanted[a]:
                    for f, jpeg in entries:
                        clip.proxy[f // step] = jpeg
                else:
                    missing.append((a, b))
            if cache and len(missing) < len(parts):
                cache.touch(fp)
            _emit(self.signals.progress, clip)
            runs = []                                    # consecutive missing chunks together
            for a, b in missing:
                if runs and runs[-1][1] == a:
                    runs[-1] = (runs[-1][0], b)
                else:
                    runs.append((a, b))
            chunk_of = {f: a for a, b in parts for f in wanted[a]}
            left = {a: len(wanted[a]) for a, _ in missing}
            last = time.monotonic()
            for ra, rb in runs:
                if clip.removed:
                    break
                selected = [f for f in range(ra, rb) if f % step == 0]
                proc = subprocess.Popen(preview.proxy_args(clip.info, frames, ra, rb),
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        stdin=subprocess.DEVNULL, **ffmpeg_bin.POPEN_FLAGS)
                buffer, n = bytearray(), 0
                try:
                    while not clip.removed:
                        block = proc.stdout.read(1 << 16)
                        if not block:
                            break
                        buffer += block
                        for jpeg in preview.split_jpegs(buffer):
                            if n < len(selected):
                                f = selected[n]
                                clip.proxy[f // step] = jpeg
                                a = chunk_of[f]
                                left[a] -= 1
                                if left[a] == 0 and cache:      # chunk complete: store it
                                    b = next(e for s, e in parts if s == a)
                                    try:
                                        cache.save_chunk(fp, header(a, b), a,
                                                         [(g, clip.proxy[g // step]) for g in wanted[a]])
                                    except OSError:
                                        pass
                            n += 1
                        if time.monotonic() - last > 0.5:
                            last = time.monotonic()
                            if not _emit(self.signals.progress, clip):
                                break
                finally:
                    proc.kill()
                    proc.wait()
            clip.proxy_done = True
            _emit(self.signals.progress, clip)


def start(task: QRunnable) -> None:
    QThreadPool.globalInstance().start(task)


class Player(QObject):
    """Plays a PlayPlan: ffmpeg decodes into a pipe, a thread shows each frame on time.

    If decoding is too slow, late frames are skipped (but at least ~25 pictures per second
    are shown) and `behind` reports that playback runs slower than the export will.
    """
    frame = Signal(object, int, bool)   # QImage, source frame, behind
    finished = Signal(str)               # "" or an error message

    MIN_SHOW = 0.04       # show a late frame if the last one is older than this
    BEHIND = 0.25         # seconds of delay that count as "can't keep up"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._generation = 0

    @property
    def playing(self) -> bool:
        return self._proc is not None

    def play(self, plan: playback.PlayPlan) -> None:
        self.stop()
        self._generation += 1
        self._proc = subprocess.Popen(plan.args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      stdin=subprocess.DEVNULL, **ffmpeg_bin.POPEN_FLAGS)
        threading.Thread(target=self._run, args=(self._proc, plan, self._generation),
                         daemon=True).start()

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        self._generation += 1
        if proc:
            proc.kill()

    def _run(self, proc, plan: playback.PlayPlan, generation: int) -> None:
        w, h = plan.size
        size = w * h * 3
        period = 1 / float(plan.fps)
        t0 = last_shown = None
        n = 0
        while generation == self._generation:
            data = proc.stdout.read(size)
            if len(data) < size:
                break
            now = time.monotonic()
            if t0 is None:
                t0 = now           # the clock starts with the first decoded frame
            due = t0 + n * period
            late = now - due
            if late < 0:
                time.sleep(-late)
            elif late > period and last_shown is not None and now - last_shown < self.MIN_SHOW:
                n += 1
                continue
            if generation != self._generation:
                break
            image = QImage(data, w, h, w * 3, QImage.Format_RGB888).copy()
            last_shown = time.monotonic()
            if not _emit(self.frame, image, plan.source_frame(n), late > self.BEHIND):
                break
            n += 1
        proc.wait()
        message = ""
        if proc.returncode not in (0, None) and generation == self._generation:
            message = proc.stderr.read().decode("utf-8", "replace").strip() or "ffmpeg failed"
        proc.stderr.close()
        proc.stdout.close()
        if generation == self._generation:
            self._generation += 1
            self._proc = None
            _emit(self.finished, message)
