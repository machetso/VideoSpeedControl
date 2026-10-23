"""Preview of the frame at the playhead, a thumbnail timeline with keyframe markers, and
in/out points.

In mode A (lossless retime) in/out points snap to keyframes; otherwise they are frame-exact.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from ..core import preview
from ..core.job import KEYFRAME_TRIM_REASON
from .clips import Clip, Status, fmt_duration
from . import workers

MARGIN = 8
THUMB_BAND = 56
KEY_BAND = 14
HANDLE_GRAB = 6
TRIM_COLOR = QColor("#f1c40f")
PLAYHEAD_COLOR = QColor("#e74c3c")


class Timeline(QWidget):
    seek = Signal(int)          # frame index
    in_moved = Signal(int)      # requested first frame
    out_moved = Signal(int)     # requested last frame (inclusive)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip: Clip | None = None
        self.snaps = False
        self._drag: str | None = None
        self.setMinimumHeight(THUMB_BAND + KEY_BAND + 10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(THUMB_BAND + KEY_BAND + 10)
        return size

    # ------------------------------------------------------------------ geometry

    @property
    def count(self) -> int:
        return self.clip.frames.count if self.clip and self.clip.frames else 0

    def _span(self) -> float:
        return max(1.0, self.width() - 2 * MARGIN)

    def x_of(self, frame: float) -> float:
        """Left edge of a frame (or a boundary between frames)."""
        return MARGIN + frame / max(1, self.count) * self._span()

    def frame_at(self, x: float) -> int:
        f = math.floor((x - MARGIN) / self._span() * self.count)
        return max(0, min(f, self.count - 1))

    def boundary_at(self, x: float) -> int:
        b = round((x - MARGIN) / self._span() * self.count)
        return max(0, min(b, self.count))

    def _trim_edges(self) -> tuple[float, float]:
        trim = self.clip.trim
        end = trim.end if trim.end is not None else self.count
        return self.x_of(trim.start), self.x_of(end)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#202020"))
        if not self.count:
            p.setPen(QColor("#888"))
            text = "Scanning frames…" if self.clip and self.clip.info else ""
            p.drawText(self.rect(), Qt.AlignCenter, text)
            return
        span = self._span()
        clip = self.clip

        # thumbnails, each tile center-cropped to its slot
        n = workers.THUMB_COUNT
        tile = span / n
        for slot, item in enumerate(clip.thumbs):
            if not item:
                continue
            img = item[1]
            target = QRectF(MARGIN + slot * tile, 0, tile, THUMB_BAND)
            scale = THUMB_BAND / img.height()
            src_w = min(img.width(), tile / scale)
            source = QRectF((img.width() - src_w) / 2, 0, src_w, img.height())
            p.drawImage(target, img, source)

        # keyframe ticks (one per pixel column at most)
        key_top = THUMB_BAND + 2
        p.setPen(QPen(TRIM_COLOR if self.snaps else QColor("#9a9a9a"), 1))
        columns = {int(self.x_of(k)) for k in clip.frames.keyframes}
        for x in columns:
            p.drawLine(x, key_top, x, key_top + KEY_BAND - 4)

        # everything outside the trim range is dimmed
        x_in, x_out = self._trim_edges()
        shade = QColor(0, 0, 0, 170)
        p.fillRect(QRectF(MARGIN, 0, x_in - MARGIN, self.height()), shade)
        p.fillRect(QRectF(x_out, 0, MARGIN + span - x_out, self.height()), shade)

        # in / out brackets
        p.setPen(QPen(TRIM_COLOR, 3))
        h = self.height() - 1
        for x, d in ((x_in, 1), (x_out, -1)):
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            p.drawLine(QPointF(x, 1), QPointF(x + 7 * d, 1))
            p.drawLine(QPointF(x, h), QPointF(x + 7 * d, h))

        # playhead in the middle of its frame
        x = self.x_of(clip.playhead + 0.5)
        p.setPen(QPen(PLAYHEAD_COLOR, 2))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))

    # ------------------------------------------------------------------ mouse

    def _handle_at(self, x: float) -> str | None:
        x_in, x_out = self._trim_edges()
        d_in, d_out = abs(x - x_in), abs(x - x_out)
        if min(d_in, d_out) > HANDLE_GRAB:
            return None
        return "in" if d_in <= d_out else "out"

    def mousePressEvent(self, event) -> None:
        if not self.count or event.button() != Qt.LeftButton:
            return
        x = event.position().x()
        self._drag = self._handle_at(x) or "seek"
        self._drag_to(x)

    def mouseMoveEvent(self, event) -> None:
        if not self.count:
            return
        x = event.position().x()
        if self._drag:
            self._drag_to(x)
        else:
            self.setCursor(Qt.SizeHorCursor if self._handle_at(x) else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None

    def _drag_to(self, x: float) -> None:
        if self._drag == "seek":
            self.seek.emit(self.frame_at(x))
        elif self._drag == "in":
            self.in_moved.emit(self.boundary_at(x))
        elif self._drag == "out":
            self.out_moved.emit(self.boundary_at(x) - 1)

    def wheelEvent(self, event) -> None:
        if self.count and self.clip:
            step = -1 if event.angleDelta().y() > 0 else 1
            self.seek.emit(self.clip.playhead + step)


class FrameView(QLabel):
    """Shows a QImage scaled to fit, keeping its aspect ratio."""
    resized = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(160, 90)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setStyleSheet("background:#111; color:#888;")

    def set_image(self, image) -> None:
        self.image = image
        self._rescale()

    def clear_image(self, text: str = "") -> None:
        self.image = None
        self.clear()
        self.setText(text)

    def _rescale(self) -> None:
        if self.image is None or self.image.isNull():
            return
        pix = QPixmap.fromImage(self.image)
        dpr = self.devicePixelRatioF()
        pix = pix.scaled(self.size() * dpr, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        self.setPixmap(pix)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()
        self.resized.emit()


class PreviewPanel(QWidget):
    trim_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip: Clip | None = None
        self._busy = False                # one frame decode at a time; the latest request wins
        self._shown: tuple | None = None  # (path, frame, size) of the image on screen
        self._requested: tuple | None = None
        self.frame_signals = workers.FrameSignals(self)
        self.frame_signals.frame.connect(self._frame_ready)
        self.frame_signals.failed.connect(self._frame_failed)
        self._resize_timer = QTimer(self, singleShot=True, interval=150,
                                    timeout=self._request_frame)

        self.view = FrameView()
        self.view.resized.connect(self._resize_timer.start)
        self.timeline = Timeline()
        self.timeline.seek.connect(self.seek)
        self.timeline.in_moved.connect(self.set_in)
        self.timeline.out_moved.connect(self.set_out)

        def button(text, tip, slot):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        self.frame_spin = QSpinBox()
        self.frame_spin.setToolTip("Frame number at the playhead (0 = first frame)")
        self.frame_spin.setKeyboardTracking(False)
        self.frame_spin.valueChanged.connect(self.seek)
        self.position = QLabel()
        transport = QHBoxLayout()
        transport.addWidget(button("⏮", "First frame (Home)", lambda: self.seek(0)))
        transport.addWidget(button("◀◀", "Previous keyframe (Shift+←)", lambda: self.step_key(-1)))
        transport.addWidget(button("◀", "Previous frame (←)", lambda: self.step(-1)))
        transport.addWidget(self.frame_spin)
        transport.addWidget(button("▶", "Next frame (→)", lambda: self.step(1)))
        transport.addWidget(button("▶▶", "Next keyframe (Shift+→)", lambda: self.step_key(1)))
        transport.addWidget(button("⏭", "Last frame (End)", lambda: self.seek(10**9)))
        transport.addWidget(self.position, 1)

        self.in_button = QPushButton("Set in (I)")
        self.in_button.setToolTip("First frame of the output = frame at the playhead")
        self.in_button.clicked.connect(lambda: self.set_in(self.clip.playhead))
        self.out_button = QPushButton("Set out (O)")
        self.out_button.setToolTip("Last frame of the output = frame at the playhead")
        self.out_button.clicked.connect(lambda: self.set_out(self.clip.playhead))
        self.clear_button = QPushButton("Clear trim")
        self.clear_button.clicked.connect(self.clear_trim)
        self.snap_button = QPushButton("Snap to keyframes")
        self.snap_button.setToolTip(KEYFRAME_TRIM_REASON)
        self.snap_button.clicked.connect(self.snap_trim)
        self.trim_label = QLabel()
        trim_row = QHBoxLayout()
        for w in (self.in_button, self.out_button, self.clear_button, self.snap_button):
            trim_row.addWidget(w)
        trim_row.addWidget(self.trim_label, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setToolTip(KEYFRAME_TRIM_REASON)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.timeline)
        layout.addLayout(transport)
        layout.addLayout(trim_row)
        layout.addWidget(self.note)

        keys = ((Qt.Key_Left, lambda: self.step(-1)), (Qt.Key_Right, lambda: self.step(1)),
                (Qt.SHIFT | Qt.Key_Left, lambda: self.step_key(-1)),
                (Qt.SHIFT | Qt.Key_Right, lambda: self.step_key(1)),
                (Qt.Key_Home, lambda: self.seek(0)), (Qt.Key_End, lambda: self.seek(10**9)),
                (Qt.Key_I, lambda: self.set_in(self.clip.playhead)),
                (Qt.Key_O, lambda: self.set_out(self.clip.playhead)))
        for key, slot in keys:
            sc = QShortcut(QKeySequence(key), self, context=Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda slot=slot: self._ready() and slot())
        self.set_clip(None)

    # ------------------------------------------------------------------ public

    def set_clip(self, clip: Clip | None) -> None:
        if clip is not self.clip:
            self.note.clear()
            self._shown = None
            self.view.clear_image()
        self.clip = clip
        self.timeline.clip = clip
        self.refresh()

    def refresh(self) -> None:
        """Re-read the clip (trim, mode, frames) – e.g. after settings changed."""
        ready = self._ready()
        for w in (self.frame_spin, self.in_button, self.out_button, self.clear_button,
                  self.timeline):
            w.setEnabled(ready)
        for b in self.findChildren(QToolButton):
            b.setEnabled(ready)
        if not ready:
            clip = self.clip
            if clip is None:
                text = ""
            elif clip.status == Status.ERROR:
                text = clip.error
            else:
                text = clip.status.value
            self.view.clear_image(text)
            self.position.clear()
            self.trim_label.clear()
            self.snap_button.hide()
            self.timeline.update()
            return
        clip, job = self.clip, self.clip.job
        self.timeline.snaps = job.snaps_to_keyframes
        clip.playhead = max(0, min(clip.playhead, job.total_frames - 1))
        self.frame_spin.blockSignals(True)
        self.frame_spin.setRange(0, job.total_frames - 1)
        self.frame_spin.setValue(clip.playhead)
        self.frame_spin.blockSignals(False)
        self._update_labels()
        self.timeline.update()
        self._request_frame()

    def thumbnail_arrived(self, clip: Clip) -> None:
        if clip is self.clip:
            self.timeline.update()

    # ------------------------------------------------------------------ navigation

    def _ready(self) -> bool:
        return bool(self.clip and self.clip.frames and self.clip.frames.count)

    def seek(self, frame: int) -> None:
        if not self._ready():
            return
        self.clip.playhead = max(0, min(int(frame), self.clip.frames.count - 1))
        self.refresh()

    def step(self, delta: int) -> None:
        self.seek(self.clip.playhead + delta)

    def step_key(self, direction: int) -> None:
        fm, ph = self.clip.frames, self.clip.playhead
        if direction < 0:
            target = fm.keyframe_at_or_before(ph - 1) if ph > 0 else 0
        else:
            target = fm.keyframe_after(ph)
            if target >= fm.count:
                target = fm.count - 1
        self.seek(target)

    # ------------------------------------------------------------------ trim

    def set_in(self, frame: int) -> None:
        if not self._ready():
            return
        trim = self.clip.job.trim_with_in(frame)
        self._snap_note("In-point", frame, trim.start)
        self._set_trim(trim)

    def set_out(self, last: int) -> None:
        if not self._ready():
            return
        job = self.clip.job
        trim = job.trim_with_out(last)
        end = trim.end if trim.end is not None else job.total_frames
        self._snap_note("Out-point", last, end - 1)
        self._set_trim(trim)

    def clear_trim(self) -> None:
        self.note.clear()
        self._set_trim(type(self.clip.trim)())

    def snap_trim(self) -> None:
        self.note.clear()
        self._set_trim(self.clip.job.snapped_trim())

    def _set_trim(self, trim) -> None:
        if trim != self.clip.trim:
            self.clip.trim = trim
            self.refresh()
            self.trim_changed.emit()

    def _snap_note(self, what: str, wanted: int, got: int) -> None:
        if self.clip.job.snaps_to_keyframes and wanted != got:
            self.note.setText(f"{what} moved to frame {got} (you chose {wanted}): lossless "
                              "retime can only cut at keyframes. Hover for details, or choose "
                              "a codec to cut frame-exactly.")
        else:
            self.note.clear()

    # ------------------------------------------------------------------ frame preview

    def _wanted(self) -> tuple | None:
        if not self._ready():
            return None
        dpr = self.view.devicePixelRatioF()
        size = preview.fit_size(self.clip.info, min(1920, int(self.view.width() * dpr)),
                                min(1080, int(self.view.height() * dpr)))
        return self.clip.path, self.clip.playhead, size

    def _request_frame(self) -> None:
        wanted = self._wanted()
        if self._busy or wanted is None or wanted == self._shown:
            return
        self._busy = True
        workers.start(workers.FrameGrabber(self.clip, wanted[1], wanted[2], self.frame_signals))
        self._requested = wanted

    def _frame_ready(self, path, index: int, image) -> None:
        self._busy = False
        if self.clip and path == self.clip.path:
            self.view.set_image(image)
            self._shown = self._requested
        self._request_frame()      # the playhead may have moved meanwhile

    def _frame_failed(self, path, index: int, message: str) -> None:
        self._busy = False
        if self.clip and path == self.clip.path:
            self.view.clear_image(message)
            self._shown = self._requested   # do not retry the same frame endlessly
        self._request_frame()

    # ------------------------------------------------------------------ labels

    def _update_labels(self) -> None:
        clip, job = self.clip, self.clip.job
        fm, ph = clip.frames, clip.playhead
        t = fm.times[ph] - fm.times[0]
        text = f"Frame {ph} of {fm.count - 1}  ·  {fmt_duration(t)}{_key_text(fm, ph)}"
        start = clip.trim.start
        end = clip.trim.end if clip.trim.end is not None else fm.count
        if start <= ph < end:
            out_t = (ph - start) / float(clip.info.fps * job.speed)
            text += f"  ·  output {fmt_duration(out_t)}"
        else:
            text += "  ·  outside the trim range"
        self.position.setText(text)

        if start == 0 and end == fm.count:
            trim = f"Whole clip: {fm.count} frames"
        else:
            trim = (f"In {start}  ·  Out {end - 1}  ·  {end - start} of {fm.count} frames")
        trim += f"  →  {job.output_frame_count} output frames, {fmt_duration(job.output_duration)}"
        self.trim_label.setText(trim)
        self.snap_button.setVisible(job.snaps_to_keyframes and not job.trim_on_keyframes())


def _key_text(fm, frame: int) -> str:
    return "  · keyframe" if fm.keyframe_at_or_before(frame) == frame else ""
