"""Preview of the frame at the playhead, a thumbnail timeline with keyframe markers, and
in/out points.

In mode A (lossless retime) in/out points snap to keyframes; otherwise they are frame-exact.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox,
                               QPushButton, QSizePolicy, QSpinBox, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from dataclasses import replace
from fractions import Fraction

from ..core import formats, playback, preview, segments as seg, smart
from ..core.job import Mode
from ..core.job import KEYFRAME_TRIM_REASON
from .clips import (Clip, Status, fmt_duration, fmt_rate, fmt_seconds, fmt_slowdown,
                    frame_rate_choices)
from . import workers
from .zoom import ZoomState

MARGIN = 8
THUMB_BAND = 56
KEY_BAND = 14
HANDLE_GRAB = 6
TRIM_COLOR = QColor("#f1c40f")
PLAYHEAD_COLOR = QColor("#e74c3c")
SECTION_COLOR = QColor(52, 152, 219, 210)
PENDING_COLOR = QColor(26, 188, 156)
SECTION_BAND = 14
MAGNET_PX = 8           # the cursor snaps to section borders closer than this
EXACT_DELAY_MS = 120    # sharp frame once the cursor rests this long (small copy meanwhile)
SPEEDUP_FACTORS = (2, 3, 4, 6, 8)   # sections faster than real time: rate = k × original
LABEL_INTERVAL = 0.1    # seconds between label updates while playing


class Timeline(QWidget):
    seek = Signal(int)          # frame index
    in_moved = Signal(int)      # requested first frame
    out_moved = Signal(int)     # requested last frame (inclusive)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip: Clip | None = None
        self.pending: tuple[int | None, int | None] = (None, None)   # section being marked
        self.keys: list[int] | None = None    # keyframes usable for cuts (smart: safe ones)
        self.magnetic = True
        self.magnet_hit: int | None = None    # boundary the cursor snapped to (drawn)
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
        keys = self.keys if self.keys is not None else clip.frames.keyframes
        columns = {int(self.x_of(k)) for k in keys}
        for x in columns:
            p.drawLine(x, key_top, x, key_top + KEY_BAND - 4)

        # everything outside the trim range is dimmed
        x_in, x_out = self._trim_edges()
        shade = QColor(0, 0, 0, 170)
        p.fillRect(QRectF(MARGIN, 0, x_in - MARGIN, self.height()), shade)
        p.fillRect(QRectF(x_out, 0, MARGIN + span - x_out, self.height()), shade)

        # speed sections: a labelled band at the bottom of the thumbnails
        band_top = THUMB_BAND - SECTION_BAND
        for s in clip.segments:
            r = QRectF(self.x_of(s.start), band_top, self.x_of(s.end) - self.x_of(s.start),
                       SECTION_BAND)
            p.fillRect(r, SECTION_COLOR)
            p.setPen(QColor("white"))
            text = f"{fmt_rate(s.fps)} fps"
            if r.width() > p.fontMetrics().horizontalAdvance(text) + 4:
                p.drawText(r, Qt.AlignCenter, text)
        a, b = self.pending
        if a is not None:
            b = a if b is None else b
            lo, hi = min(a, b), max(a, b) + 1
            p.setPen(QPen(PENDING_COLOR, 2, Qt.DashLine))
            p.drawRect(QRectF(self.x_of(lo), 1, self.x_of(hi) - self.x_of(lo), THUMB_BAND - 2))

        # the section border the cursor is magnetically attached to
        if self.magnet_hit is not None:
            x = self.x_of(self.magnet_hit)
            p.setPen(QPen(PENDING_COLOR, 3))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))

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
        if self.magnet_hit is not None:
            self.magnet_hit = None
            self.update()

    def magnet_targets(self) -> list[tuple[int, int]]:
        """(frame, border) pairs the cursor can snap to.

        Before a section start is marked: the first frame after each section (seamless
        continuation). While marking the end: the last frame before each section.
        """
        clip = self.clip
        if not clip or not clip.segments:
            return []
        start, end = self.pending
        if start is None or end is not None:
            out = [(s.end, s.end) for s in clip.segments]
        else:
            out = [(s.start - 1, s.start) for s in clip.segments]
        return [(f, b) for f, b in out if 0 <= f < self.count]

    def _snap(self, x: float) -> int:
        frame = self.frame_at(x)
        self.magnet_hit = None
        if self.magnetic:
            near = [(abs(x - self.x_of(f + 0.5)), f, b) for f, b in self.magnet_targets()]
            near = [n for n in near if n[0] <= MAGNET_PX]
            if near:
                _, frame, self.magnet_hit = min(near)
        return frame

    def _drag_to(self, x: float) -> None:
        if self._drag == "seek":
            self.seek.emit(self._snap(x))
        elif self._drag == "in":
            self.in_moved.emit(self.boundary_at(x))
        elif self._drag == "out":
            self.out_moved.emit(self.boundary_at(x) - 1)

    def wheelEvent(self, event) -> None:
        if self.count and self.clip:
            step = -1 if event.angleDelta().y() > 0 else 1
            self.seek.emit(self.clip.playhead + step)


class FrameView(QWidget):
    """Shows a frame fitted or at 1:1 / 2:1 zoom; drag pans, double-click toggles."""
    resized = Signal()

    def __init__(self, zoom: ZoomState, parent=None):
        super().__init__(parent)
        self.zoom = zoom
        self.zoom.changed.connect(self.update)
        self.image = None
        self.native: tuple[int, int] | None = None   # full size of the footage
        self.text = ""
        self._drag: QPointF | None = None
        self.setMinimumSize(160, 90)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def set_image(self, image) -> None:
        self.image, self.text = image, ""
        self.update()

    def clear_image(self, text: str = "") -> None:
        self.image, self.text = None, text
        self.update()

    def drawn_rect(self) -> QRectF:
        w, h = self.native or (self.image.width(), self.image.height())
        return self.zoom.rect(w, h, QRectF(self.rect()), self.devicePixelRatioF())

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111"))
        if self.image is None or self.image.isNull():
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.text)
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom.zoom is None)
        p.drawImage(self.drawn_rect(), self.image)

    def mousePressEvent(self, event) -> None:
        if self.zoom.zoom is not None:
            self._drag = event.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and self.native:
            self.zoom.pan(event.position() - self._drag, *self.native, self.devicePixelRatioF())
            self._drag = event.position()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.image is not None:
            self.zoom.toggle_at(event.position(), self.drawn_rect())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class PreviewPanel(QWidget):
    trim_changed = Signal()
    add_to_batch = Signal(object)    # clip – export it later as it is now

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip: Clip | None = None
        self.fetcher = workers.FrameFetcher(self)
        self.fetcher.ready.connect(self._fetched)
        self.fetcher.failed.connect(lambda message: self.view.clear_image(message))
        self.player = workers.Player(self)
        self.player.frame.connect(self._played)
        self.player.finished.connect(self._play_finished)
        self._play_note = ""
        self._labels_at = 0.0
        self._table_key = None
        self._exact_size = (0, 0)
        self._exact_timer = QTimer(self, singleShot=True, interval=EXACT_DELAY_MS,
                                   timeout=self._request_exact)
        self._resize_timer = QTimer(self, singleShot=True, interval=150,
                                    timeout=self._request_frame)

        self.zoom = ZoomState(self)
        self.zoom.changed.connect(self._request_frame)   # 1:1 needs the full-size frame
        self.view = FrameView(self.zoom)
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
        # changing text must never resize the layout (the view would jump during playback)
        self.position.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.play_button = QPushButton("▶ Play preview")
        self.play_button.setFixedWidth(self.play_button.sizeHint().width())
        self.play_button.setToolTip(
            "Play the output at the chosen frame rate and speed (Space).\n"
            "Reduced size, nothing is encoded – starts instantly.\n"
            "Plays from the playhead to the out-point.")
        self.play_button.clicked.connect(self.toggle_play)
        transport = QHBoxLayout()
        transport.addWidget(self.play_button)
        transport.addWidget(button("⏮", "First frame (Home)", lambda: self.seek(0)))
        transport.addWidget(button("◀◀", "Previous keyframe (Shift+←)", lambda: self.step_key(-1)))
        transport.addWidget(button("◀", "Previous frame (←)", lambda: self.step(-1)))
        transport.addWidget(self.frame_spin)
        transport.addWidget(button("▶", "Next frame (→)", lambda: self.step(1)))
        transport.addWidget(button("▶▶", "Next keyframe (Shift+→)", lambda: self.step_key(1)))
        transport.addWidget(button("⏭", "Last frame (End)", lambda: self.seek(10**9)))
        transport.addWidget(self.position, 1)
        transport.addWidget(self.zoom.combo())

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
        self.trim_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        trim_row = QHBoxLayout()
        for w in (self.in_button, self.out_button, self.clear_button, self.snap_button):
            trim_row.addWidget(w)
        trim_row.addWidget(self.trim_label, 1)
        self.key_hint = QLabel()
        self.key_hint.setWordWrap(True)
        self.key_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.key_hint.setStyleSheet("color: #b7950b")
        self.key_hint.setToolTip(KEYFRAME_TRIM_REASON)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.note.setFixedHeight(2 * self.note.fontMetrics().lineSpacing() + 4)
        self.note.setToolTip(KEYFRAME_TRIM_REASON)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.timeline)
        layout.addLayout(transport)
        layout.addLayout(trim_row)
        layout.addLayout(self._build_sections())
        layout.addWidget(self.sections_table)
        layout.addLayout(self._build_batch_row())
        layout.addWidget(self.key_hint)
        layout.addWidget(self.note)

        keys = ((Qt.Key_Left, lambda: self.step(-1)), (Qt.Key_Right, lambda: self.step(1)),
                (Qt.SHIFT | Qt.Key_Left, lambda: self.step_key(-1)),
                (Qt.SHIFT | Qt.Key_Right, lambda: self.step_key(1)),
                (Qt.Key_Home, lambda: self.seek(0)), (Qt.Key_End, lambda: self.seek(10**9)),
                (Qt.Key_Space, self.toggle_play),
                (Qt.Key_BracketLeft, self.section_start), (Qt.Key_BracketRight, self.section_end),
                (QKeySequence.Undo, self.undo_clear),
                (Qt.Key_I, lambda: self.set_in(self.clip.playhead)),
                (Qt.Key_O, lambda: self.set_out(self.clip.playhead)))
        for key, slot in keys:
            sc = QShortcut(QKeySequence(key), self, context=Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda slot=slot: self._ready() and slot())
        self.set_clip(None)

    # ------------------------------------------------------------------ public

    def set_clip(self, clip: Clip | None) -> None:
        self._stop_playback()
        if clip is not self.clip:
            self.timeline.pending = (None, None)
            self.note.clear()
            self.fetcher.reset()
            self.view.clear_image()
        self.clip = clip
        self.timeline.clip = clip
        self.refresh()

    def refresh(self) -> None:
        """Re-read the clip (trim, mode, frames) – e.g. after settings changed."""
        self._stop_playback()
        ready = self._ready()
        for w in (self.frame_spin, self.in_button, self.out_button, self.clear_button,
                  self.timeline, self.play_button):
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
            self.key_hint.hide()
            self._update_sections()
            self.timeline.update()
            return
        clip, job = self.clip, self.clip.job
        self.timeline.snaps = job.snaps_to_keyframes
        self.timeline.keys = job.frames.keyframes if job.frames else None
        clip.playhead = max(0, min(clip.playhead, job.total_frames - 1))
        self.frame_spin.blockSignals(True)
        self.frame_spin.setRange(0, job.total_frames - 1)
        self.frame_spin.setValue(clip.playhead)
        self.frame_spin.blockSignals(False)
        self._update_labels()
        self._update_sections()
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

    def _request_frame(self) -> None:
        if not self._ready() or self.player.playing:
            return
        info = self.clip.info
        self.view.native = info.display_size
        if self.zoom.zoom is None:
            dpr = self.view.devicePixelRatioF()
            size = preview.fit_size(info, min(1920, int(self.view.width() * dpr)),
                                    min(1080, int(self.view.height() * dpr)))
        else:
            size = info.display_size        # every pixel, for 1:1 / 2:1
        self._exact_size = size
        frame = self.clip.playhead
        if self.fetcher.shown != (self.clip.path, frame, size):
            image = self._quick_image(frame)
            if image is not None:
                self.view.set_image(image)
                self.fetcher.supersede()   # the sharp frame is requested once the cursor rests
        self._exact_timer.start()

    def _request_exact(self) -> None:
        if self._ready() and not self.player.playing:
            self.fetcher.request(self.clip, self.clip.playhead, self._exact_size)

    def _quick_image(self, frame: int):
        """Small copy of `frame` (instant), else the nearest earlier thumbnail, else None."""
        clip = self.clip
        if clip.proxy:
            i = min(frame // clip.proxy_step, len(clip.proxy) - 1)
            data = clip.proxy[i]
            if data is not None:
                image = QImage.fromData(data, "JPG")
                if not image.isNull():
                    return image
        thumbs = [t for t in clip.thumbs if t and t[0] <= frame]
        return max(thumbs, key=lambda t: t[0])[1] if thumbs else None

    def proxy_progress(self, clip: Clip) -> None:
        if clip is self.clip and self._ready() and not self.player.playing:
            self._update_labels()

    # ------------------------------------------------------------------ speed sections

    def _build_sections(self) -> QHBoxLayout:
        self.sec_start_button = QPushButton("Section start [")
        self.sec_start_button.setToolTip("Mark the frame at the playhead as the first frame of a "
                                         "speed section ([).")
        self.sec_start_button.clicked.connect(self.section_start)
        self.sec_end_button = QPushButton("Section end ]")
        self.sec_end_button.setToolTip("Mark the frame at the playhead as the last frame of the "
                                       "section (]).")
        self.sec_end_button.clicked.connect(self.section_end)
        self.sec_fps = QComboBox()
        self.sec_fps.setToolTip("Frame rate of the section: each of its frames is shown for "
                                "1/fps seconds.\nThe rest of the clip plays in real time.")
        self.sec_add = QPushButton("Add section")
        self.sec_add.setToolTip(
            "Play the marked frames at the chosen frame rate.\n"
            "Sections can start at any frame – even without re-encoding, because no frame is "
            "cut:\nonly the time each frame is shown changes.")
        self.sec_add.clicked.connect(self.add_section)
        self.magnet_button = QToolButton()
        self.magnet_button.setText("🧲")
        self.magnet_button.setCheckable(True)
        self.magnet_button.setToolTip(
            "Magnetic cursor: when you drag near a section, the cursor snaps to the frame right\n"
            "after it (to start the next section seamlessly) or – while you mark an end – to\n"
            "the frame right before the next section. Click to switch it off.")
        self.magnet_button.setChecked(_setting("preview/magnetic", True))
        self.timeline.magnetic = self.magnet_button.isChecked()
        self.magnet_button.toggled.connect(self._set_magnetic)
        self.sec_label = QLabel()
        self.sec_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row = QHBoxLayout()
        for w in (self.magnet_button, self.sec_start_button, self.sec_end_button, self.sec_fps,
                  self.sec_add):
            row.addWidget(w)
        row.addWidget(self.sec_label, 1)

        t = self.sections_table = QTableWidget(0, 7)
        t.setHorizontalHeaderLabels(["Frames", "Frame rate", "Speed", "Length", "Re-encode",
                                     "Output fps", ""])
        t.horizontalHeaderItem(4).setToolTip("Smart re-encode: re-encode this section (source "
                                             "codec) – everything else is copied.")
        t.horizontalHeaderItem(5).setToolTip("Constant frame rate of the re-encoded section.")
        t.verticalHeader().hide()
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = t.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        t.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        t.setFixedHeight(t.horizontalHeader().sizeHint().height() + 3 * 28 + 4)
        t.cellClicked.connect(lambda row, _: self._seek_section(row))
        t.hide()
        return row

    def _build_batch_row(self) -> QHBoxLayout:
        self.batch_button = QPushButton("➕ Add to batch")
        self.batch_button.setToolTip(
            "Add this clip as it is now – processing mode, output settings, trim and speed\n"
            "sections – to the batch list (Export tab). The sections stay here, so you can add\n"
            "the same clip again, e.g. once lossless and once with smart re-encode.")
        self.batch_button.clicked.connect(lambda: self.clip and self.add_to_batch.emit(self.clip))
        self.clear_sections_button = QPushButton("Clear sections")
        self.clear_sections_button.setToolTip("Remove all speed sections of this clip "
                                              "(can be undone)")
        self.clear_sections_button.clicked.connect(self._confirm_clear)
        self.undo_button = QPushButton("↶ Undo")
        self.undo_button.setToolTip("Bring back the sections that were just cleared (Ctrl+Z)")
        self.undo_button.clicked.connect(self.undo_clear)
        self.undo_button.hide()
        self._cleared: tuple[Clip, list] | None = None
        row = QHBoxLayout()
        row.addWidget(self.batch_button)
        row.addStretch(1)                # far from "Add to batch" – no accidental clicks
        row.addWidget(self.undo_button)
        row.addWidget(self.clear_sections_button)
        return row

    def _confirm_clear(self) -> None:
        if not self._ready() or not self.clip.segments:
            return
        n = len(self.clip.segments)
        answer = QMessageBox.question(
            self, "Clear sections",
            f"Remove all {n} speed section{'s' * (n != 1)} of {self.clip.path.name}?\n\n"
            "You can bring them back with “Undo” (Ctrl+Z).",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Yes:
            self.clear_sections()

    def clear_sections(self) -> None:
        if not self._ready() or not self.clip.segments:
            return
        self._cleared = (self.clip, list(self.clip.segments))
        self.clip.segments.clear()
        self.timeline.pending = (None, None)
        self._sections_changed()
        self.undo_button.show()          # after _sections_changed, which hides it

    def undo_clear(self) -> None:
        if not self._cleared or self._cleared[0] is not self.clip:
            return
        clip, segments = self._cleared
        clip.segments[:] = segments
        self._cleared = None
        self._sections_changed()

    def _set_magnetic(self, on: bool) -> None:
        self.timeline.magnetic = on
        QSettings().setValue("preview/magnetic", on)

    def _rate_items(self) -> list[tuple[str, str]]:
        """Slower rates (standard frame rates), the original, and speed-ups up to 8×."""
        real = self.clip.info.real_fps
        items = [(f"{label} – {fmt_slowdown(float(real / fps))}", str(fps))
                 for label, fps in frame_rate_choices(real) if fps <= real]
        items += [(f"{fmt_rate(real * k)} fps – {k}× faster", str(real * k))
                  for k in SPEEDUP_FACTORS]
        return items

    def section_start(self) -> None:
        if self._ready():
            self.timeline.pending = (self.clip.playhead, self.timeline.pending[1])
            self._sections_changed(emit=False)

    def section_end(self) -> None:
        if self._ready():
            start = self.timeline.pending[0]
            self.timeline.pending = (self.clip.trim.start if start is None else start,
                                     self.clip.playhead)
            self._sections_changed(emit=False)

    def add_section(self) -> None:
        a, b = self.timeline.pending
        if not self._ready() or a is None or b is None or self.sec_fps.currentData() is None:
            return
        new = seg.Segment(min(a, b), max(a, b) + 1, Fraction(self.sec_fps.currentData()))
        self.clip.segments[:] = seg.add(self.clip.segments, new)
        self.timeline.pending = (None, None)
        self._sections_changed()

    def remove_section(self, index: int) -> None:
        del self.clip.segments[index]
        self._sections_changed()

    def _set_section_fps(self, index: int, value: str) -> None:
        self._set_section(index, fps=Fraction(value))

    def _set_section(self, index: int, **changes) -> None:
        if self.clip and index < len(self.clip.segments):
            self.clip.segments[index] = replace(self.clip.segments[index], **changes)
            self._sections_changed()

    def _seek_section(self, row: int) -> None:
        if self.clip and row < len(self.clip.segments):
            self.seek(self.clip.segments[row].start)

    def _sections_changed(self, emit: bool = True) -> None:
        if emit and self._cleared and (self._cleared[0] is not self.clip or self.clip.segments):
            self._cleared = None          # sections edited since: nothing to undo any more
        self._stop_playback()
        self._update_sections()
        self._update_labels()
        self.timeline.update()
        if emit:
            self.trim_changed.emit()     # output length, mode and estimates change

    def _update_sections(self) -> None:
        clip = self.clip
        ready = self._ready()
        for w in (self.sec_start_button, self.sec_end_button, self.sec_fps, self.batch_button):
            w.setEnabled(ready)
        self.clear_sections_button.setEnabled(ready and bool(clip and clip.segments))
        self.undo_button.setVisible(bool(self._cleared) and self._cleared[0] is clip)
        if not ready:
            self.sec_add.setEnabled(False)
            self.sec_label.clear()
            self.sections_table.hide()
            return
        items = self._rate_items()
        current = self.sec_fps.currentData() or str(Fraction(25))
        if [(self.sec_fps.itemText(i), self.sec_fps.itemData(i))
                for i in range(self.sec_fps.count())] != items:
            self.sec_fps.clear()
            for text, data in items:
                self.sec_fps.addItem(text, data)
        idx = self.sec_fps.findData(current)
        self.sec_fps.setCurrentIndex(idx if idx >= 0 else 0)

        a, b = self.timeline.pending
        self.sec_add.setEnabled(a is not None and b is not None)
        if a is None:
            self.sec_label.setText("Mark a range with [ and ] to play it at another frame rate."
                                   if not clip.segments else "")
        elif b is None:
            self.sec_label.setText(f"Section from frame {a} – now set the end (])")
        else:
            lo, hi = min(a, b), max(a, b)
            self.sec_label.setText(f"Frames {lo}–{hi} ({hi - lo + 1}) – choose the frame rate "
                                   "and click “Add section”")

        t = self.sections_table
        t.setVisible(bool(clip.segments))
        smart_mode = clip.settings.smart
        t.setColumnHidden(4, not smart_mode)
        t.setColumnHidden(5, not smart_mode)
        key = (id(clip), tuple(clip.segments), tuple(items), smart_mode)
        if key == self._table_key:          # rebuild only on change (refresh runs on every seek)
            return
        self._table_key = key
        t.clearContents()
        t.setRowCount(len(clip.segments))
        for row, s in enumerate(clip.segments):
            n = s.end - s.start
            slower = fmt_slowdown(float(clip.info.real_fps / s.fps))
            for col, text in ((0, f"{s.start}–{s.end - 1} ({n})"), (2, slower),
                              (3, fmt_seconds(n / float(s.fps)))):
                t.setItem(row, col, QTableWidgetItem(text))
            combo = QComboBox()
            for text, data in items:
                combo.addItem(text, data)
            if combo.findData(str(s.fps)) < 0:
                combo.addItem(f"{fmt_rate(s.fps)} fps", str(s.fps))
            combo.setCurrentIndex(combo.findData(str(s.fps)))
            combo.activated.connect(lambda _, row=row, c=combo: QTimer.singleShot(
                0, lambda: self._set_section_fps(row, c.currentData())))
            t.setCellWidget(row, 1, combo)
            check = QCheckBox()
            check.setChecked(s.reencode)
            check.setToolTip("Re-encode this section with the source codec (smart re-encode)")
            check.toggled.connect(lambda on, row=row: QTimer.singleShot(
                0, lambda: self._set_section(row, reencode=on)))
            t.setCellWidget(row, 4, _centered(check))
            out = QComboBox()
            for label, fps in formats.FRAME_RATES:
                out.addItem(f"{label} fps", str(fps))
            current = str(s.out_fps or smart.DEFAULT_OUT_FPS)
            if out.findData(current) < 0:
                out.addItem(f"{fmt_rate(Fraction(current))} fps", current)
            out.setCurrentIndex(out.findData(current))
            out.setEnabled(s.reencode)
            out.activated.connect(lambda _, row=row, c=out: QTimer.singleShot(
                0, lambda: self._set_section(row, out_fps=Fraction(c.currentData()))))
            t.setCellWidget(row, 5, out)
            remove = QToolButton()
            remove.setText("✕")
            remove.setToolTip("Remove this section")
            remove.clicked.connect(lambda _=False, row=row: QTimer.singleShot(
                0, lambda: self.remove_section(row)))
            t.setCellWidget(row, 6, remove)

    # ------------------------------------------------------------------ playback

    def toggle_play(self) -> None:
        if self.player.playing:
            self._stop_playback()
            self.refresh()
            return
        if not self._ready():
            return
        clip, job = self.clip, self.clip.job
        dpr = self.view.devicePixelRatioF()
        size = preview.fit_size(clip.info, min(playback.PREVIEW_MAX[0], int(self.view.width() * dpr)),
                                min(playback.PREVIEW_MAX[1], int(self.view.height() * dpr)))
        end = clip.trim.end if clip.trim.end is not None else job.total_frames
        start = clip.playhead if clip.trim.start <= clip.playhead < end - 1 else clip.trim.start
        plan = playback.plan(job, start, size)
        if job.has_segments:
            self._play_note = (f"Playing speed sections at {fmt_rate(plan.fps)} fps "
                               f"({fmt_seconds(job.output_duration)} in total)")
        else:
            self._play_note = (f"Playing at {fmt_rate(job.settings.fps)} fps – "
                               f"{fmt_slowdown(1 / float(job.speed))}")
        if plan.note:
            self._play_note += f"  ·  {plan.note}"
        self.player.play(plan)
        self.play_button.setText("■ Stop")

    def _stop_playback(self) -> None:
        if self.player.playing:
            self.player.stop()
            self.fetcher.reset()     # the view shows a small playback frame – fetch again
            self.note.clear()
        self.play_button.setText("▶ Play preview")

    def _fetched(self, image) -> None:
        if not self.player.playing:
            self.view.set_image(image)

    def _played(self, image, frame: int, behind: bool) -> None:
        if not self.player.playing or not self._ready():
            return
        self.view.set_image(image)
        self.clip.playhead = min(frame, self.clip.frames.count - 1)
        now = time.monotonic()
        if now - self._labels_at < LABEL_INTERVAL:     # text updates cost layout work
            self.timeline.update()
            return
        self._labels_at = now
        self.frame_spin.blockSignals(True)
        self.frame_spin.setValue(self.clip.playhead)
        self.frame_spin.blockSignals(False)
        self._update_labels()
        self.timeline.update()
        note = self._play_note
        if behind:
            note += ("  ·  <span style='color:#d35400'>decoding can't keep up – the preview "
                     "plays slower than the export will</span>")
        self.note.setText(note)

    def _play_finished(self, message: str) -> None:
        self._stop_playback()
        self.note.setText(f"Preview failed: {message}" if message else "")
        self.refresh()

    # ------------------------------------------------------------------ labels

    def _update_labels(self) -> None:
        clip, job = self.clip, self.clip.job
        fm, ph = clip.frames, clip.playhead
        t = fm.times[ph] - fm.times[0]
        text = f"Frame {ph} of {fm.count - 1}  ·  {fmt_duration(t)}{_key_text(fm, ph)}"
        if clip.proxy and not clip.proxy_done:
            ready = sum(1 for p in clip.proxy if p is not None) / len(clip.proxy)
            text += f"  ·  fast preview {ready:.0%}"
        start = clip.trim.start
        end = clip.trim.end if clip.trim.end is not None else fm.count
        if start <= ph < end:
            out_t = job.output_time(ph)
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
        self.key_hint.setVisible(job.snaps_to_keyframes)
        if job.mode == Mode.SMART:
            self.key_hint.setText(
                f"🔑 Smart re-encode joins copied and re-encoded parts only at keyframes (here "
                f"every {_key_interval(job.frames)} frames): in / out points snap to them, and "
                "sections marked “Re-encode” are widened to the nearest keyframes – the extra "
                "frames are re-encoded at the speed they have anyway.")
        elif job.snaps_to_keyframes:
            self.key_hint.setText(
                f"🔑 Lossless mode: in / out points can only be set at keyframes (here every "
                f"{_key_interval(job.frames)} frames). Only keyframes are complete pictures – all other "
                "frames depend on the frames before them, so a cut elsewhere would need "
                "re-encoding. Choose a codec for frame-exact cuts. (Speed sections are not "
                "cuts – they can start at any frame.)")


def _setting(key: str, default: bool) -> bool:
    value = QSettings().value(key, default)
    return value in (True, "true", "1", 1) if not isinstance(value, bool) else value


def _centered(widget: QWidget) -> QWidget:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget, 0, Qt.AlignCenter)
    return box


def _key_interval(fm) -> int:
    """Typical distance between keyframes (median)."""
    gaps = sorted(b - a for a, b in zip(fm.keyframes, fm.keyframes[1:]))
    return gaps[len(gaps) // 2] if gaps else fm.count


def _key_text(fm, frame: int) -> str:
    return "  · keyframe" if fm.keyframe_at_or_before(frame) == frame else ""
