# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Preview of the frame at the playhead, a thumbnail timeline with keyframe markers, and
in/out points.

In mode A (lossless retime) in/out points snap to keyframes; otherwise they are frame-exact.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen,
                           QPixmap, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox,
                               QPushButton, QSizePolicy, QSpinBox, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from dataclasses import replace
from fractions import Fraction

from ..core import formats, playback, preview, segments as seg, smart
from ..core.job import Mode
from ..core.job import KEYFRAME_TRIM_REASON
from ..i18n import tr, trp
from .clips import (Clip, Status, easy_mode, fmt_duration, fmt_rate, fmt_seconds, fmt_slowdown,
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
BORDER_GRAB = 5         # a press this close to a section border drags the border
EXACT_DELAY_MS = 120    # sharp frame once the cursor rests this long (small copy meanwhile)
SPEEDUP_FACTORS = (2, 3, 4, 6, 8)   # sections faster than real time: rate = k × original
LABEL_INTERVAL = 0.1    # seconds between label updates while playing


class Timeline(QWidget):
    seek = Signal(int)          # frame index
    in_moved = Signal(int)      # requested first frame
    out_moved = Signal(int)     # requested last frame (inclusive)
    section_clicked = Signal(int)       # index of the section clicked, -1 = none
    border_grabbed = Signal(int)        # a section border is being dragged (its position)
    border_moved = Signal(int)          # … to this position
    border_released = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip: Clip | None = None
        self.pending: tuple[int | None, int | None] = (None, None)   # section being marked
        self.keys: list[int] | None = None    # keyframes usable for cuts (smart: safe ones)
        self.magnetic = True
        self.magnet_hit: int | None = None    # boundary the cursor snapped to (drawn)
        self.snaps = False
        self.dragged_border: int | None = None   # border being dragged (drawn highlighted)
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
            text = tr("Scanning frames…") if self.clip and self.clip.info else ""
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

        # speed ramps: dark field with a slanted line – up = getting faster, down = slower
        for a, b, faster in self.ramp_zones():
            x0, x1 = self.x_of(a), max(self.x_of(a) + 3, self.x_of(b))
            top = THUMB_BAND * 0.35
            p.fillRect(QRectF(x0, top, x1 - x0, band_top - top), QColor(0, 0, 0, 150))
            p.setPen(QPen(QColor("white"), 2))
            lo, hi = band_top - 3, top + 3
            p.drawLine(QPointF(x0, lo if faster else hi), QPointF(x1, hi if faster else lo))

        # section borders: clearly visible lines with a grip in the keyframe band (drag to move)
        for b in seg.borders(clip.segments, self.count):
            x = self.x_of(b)
            color = PENDING_COLOR if b == self.dragged_border else QColor("white")
            p.setPen(QPen(QColor(0, 0, 0, 200), 4))
            p.drawLine(QPointF(x, 0), QPointF(x, THUMB_BAND))
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(x, 0), QPointF(x, THUMB_BAND))
            p.setPen(QPen(QColor(0, 0, 0, 200), 1))
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x - 4, THUMB_BAND + 2, 8, KEY_BAND - 4), 2, 2)
            p.setBrush(Qt.NoBrush)

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

    def ramp_zones(self) -> list[tuple[int, int, bool]]:
        """(first frame, end, getting faster) of every speed ramp."""
        clip = self.clip
        segments = seg.all_smooth(clip.segments) if easy_mode() else clip.segments
        steps = seg.ramp_steps(segments, 0, self.count, clip.info.real_fps)
        zones: list[list] = []
        for st in steps:
            if zones and zones[-1][1] == st.start:
                zones[-1][1], zones[-1][3] = st.end, st.fps
            else:
                zones.append([st.start, st.end, st.fps, st.fps])
        return [(a, b, last > first) for a, b, first, last in zones]

    def _border_at(self, x: float) -> int | None:
        near = [(abs(x - self.x_of(b)), b) for b in seg.borders(self.clip.segments, self.count)]
        near = [n for n in near if n[0] <= BORDER_GRAB]
        return min(near)[1] if near else None

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
        self._drag = self._handle_at(x)
        if self._drag is None and (border := self._border_at(x)) is not None:
            self._drag = "border"
            self.dragged_border = border
            self.border_grabbed.emit(border)
            return
        self._drag = self._drag or "seek"
        if self._drag == "seek":
            frame = self.frame_at(x)
            self.section_clicked.emit(next((i for i, s in enumerate(self.clip.segments)
                                            if s.start <= frame < s.end), -1))
        self._drag_to(x)

    def mouseMoveEvent(self, event) -> None:
        if not self.count:
            return
        x = event.position().x()
        if self._drag:
            self._drag_to(x)
        else:
            grab = self._handle_at(x) or self._border_at(x) is not None
            self.setCursor(Qt.SizeHorCursor if grab else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag == "border":
            self.dragged_border = None
            self.border_released.emit()
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
        elif self._drag == "border":
            self.border_moved.emit(self.boundary_at(x))

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
    update_entry = Signal(object)    # clip – replace the batch entry being edited

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
        self._show_row: int | None = None     # section row to scroll into view after a rebuild
        self._selected: int | None = None     # section being edited (table row)
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
        self.timeline.section_clicked.connect(self._select_section)
        self.timeline.border_grabbed.connect(self._border_grabbed)
        self.timeline.border_moved.connect(self._border_moved)
        self.timeline.border_released.connect(self._border_released)
        self._drag_base: list | None = None       # sections before a border drag
        self._drag_from = 0

        def button(text, tip, slot):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        self.frame_spin = QSpinBox()
        self.frame_spin.setToolTip(tr("Frame number at the playhead (0 = first frame)"))
        self.frame_spin.setKeyboardTracking(False)
        self.frame_spin.valueChanged.connect(self.seek)
        self.position = QLabel()
        # changing text must never resize the layout (the view would jump during playback)
        self.position.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.play_button = QPushButton(tr("▶ Play preview"))
        self.play_button.setFixedWidth(self.play_button.sizeHint().width())
        self.play_button.setToolTip(tr(
            "Play the output at the chosen frame rate and speed (Space).\n"
            "Reduced size, nothing is encoded – starts instantly.\n"
            "Plays from the playhead to the out-point."))
        self.play_button.clicked.connect(self.toggle_play)
        transport = QHBoxLayout()
        transport.addWidget(self.play_button)
        def icon_button(kind, tip, slot):
            """Drawn symbols (fonts put the bar of ⏮ off-centre): first / last, − 🔑 / 🔑 +."""
            b = button("", tip, slot)
            b.setIcon(transport_icon(kind, self.palette().buttonText().color()))
            b.setIconSize(transport_icon_size(kind))
            return b
        transport.addWidget(icon_button("first", tr("First frame (Home)"), lambda: self.seek(0)))
        transport.addWidget(icon_button("key-", tr("Previous keyframe (Shift+←)"), lambda: self.step_key(-1)))
        transport.addWidget(button("◀ 1", tr("Previous frame (←)"), lambda: self.step(-1)))
        transport.addWidget(self.frame_spin)
        transport.addWidget(button("1 ▶", tr("Next frame (→)"), lambda: self.step(1)))
        transport.addWidget(icon_button("key+", tr("Next keyframe (Shift+→)"), lambda: self.step_key(1)))
        transport.addWidget(icon_button("last", tr("Last frame (End)"), lambda: self.seek(10**9)))
        transport.addWidget(self.position, 1)
        transport.addWidget(self.zoom.combo())

        self.in_button = QPushButton(tr("Set in (I)"))
        self.in_button.setToolTip(tr("First frame of the output = frame at the playhead"))
        self.in_button.clicked.connect(lambda: self.set_in(self.clip.playhead))
        self.out_button = QPushButton(tr("Set out (O)"))
        self.out_button.setToolTip(tr("Last frame of the output = frame at the playhead"))
        self.out_button.clicked.connect(lambda: self.set_out(self.clip.playhead))
        self.clear_button = QPushButton(tr("Clear trim"))
        self.clear_button.clicked.connect(self.clear_trim)
        self.snap_button = QPushButton(tr("Snap to keyframes"))
        self.snap_button.setToolTip(tr(KEYFRAME_TRIM_REASON))
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
        self.key_hint.setToolTip(tr(KEYFRAME_TRIM_REASON))
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.note.setFixedHeight(2 * self.note.fontMetrics().lineSpacing() + 4)
        self.note.setToolTip(tr(KEYFRAME_TRIM_REASON))

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
                (QKeySequence.Undo, self.undo), (QKeySequence.Redo, self.redo),
                (Qt.CTRL | Qt.Key_Y, self.redo),
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
                text = tr(clip.status.value)
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
        self._snap_note(tr("In-point"), frame, trim.start)
        self._set_trim(trim)

    def set_out(self, last: int) -> None:
        if not self._ready():
            return
        job = self.clip.job
        trim = job.trim_with_out(last)
        end = trim.end if trim.end is not None else job.total_frames
        self._snap_note(tr("Out-point"), last, end - 1)
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
            self.note.setText(tr("%s moved to frame %d (you chose %d): lossless "
                                 "retime can only cut at keyframes. Hover for details, or choose "
                                 "a codec to cut frame-exactly.", what, got, wanted))
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
        self.sec_start_button = QPushButton(tr("Section start ["))
        self.sec_start_button.setToolTip(tr("Mark the frame at the playhead as the first frame "
                                            "of a speed section ([)."))
        self.sec_start_button.clicked.connect(self.section_start)
        self.sec_end_button = QPushButton(tr("Section end ]"))
        self.sec_end_button.setToolTip(tr("Mark the frame at the playhead as the last frame of "
                                          "the section (])."))
        self.sec_end_button.clicked.connect(self.section_end)
        self.sec_fps = QComboBox()
        self.sec_fps.setToolTip(tr("Frame rate of the section: each of its frames is shown for "
                                   "1/fps seconds.\nThe rest of the clip plays in real time."))
        self.sec_add = QPushButton(tr("Add section"))
        self.sec_add.setToolTip(tr(
            "Play the marked frames at the chosen frame rate.\n"
            "Sections can start at any frame – even without re-encoding, because no frame is "
            "cut:\nonly the time each frame is shown changes."))
        self.sec_add.clicked.connect(self.add_section)
        self.magnet_button = QToolButton()
        self.magnet_button.setText("🧲")
        self.magnet_button.setCheckable(True)
        self.magnet_button.setToolTip(tr(
            "Magnetic cursor: when you drag near a section, the cursor snaps to the frame right\n"
            "after it (to start the next section seamlessly) or – while you mark an end – to\n"
            "the frame right before the next section. Click to switch it off."))
        self.magnet_button.setChecked(_setting("preview/magnetic", True))
        self.timeline.magnetic = self.magnet_button.isChecked()
        self.magnet_button.toggled.connect(self._set_magnetic)
        self.sel_start_button = QPushButton(tr("Start = playhead"))
        self.sel_start_button.setToolTip(tr("The selected section now starts at the playhead"))
        self.sel_start_button.clicked.connect(lambda: self._set_selected_range(start=True))
        self.sel_end_button = QPushButton(tr("End = playhead"))
        self.sel_end_button.setToolTip(tr("The selected section now ends at the playhead"))
        self.sel_end_button.clicked.connect(lambda: self._set_selected_range(start=False))
        self.sec_label = QLabel()
        self.sec_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row = QHBoxLayout()
        for w in (self.magnet_button, self.sec_start_button, self.sec_end_button, self.sec_fps,
                  self.sec_add, self.sel_start_button, self.sel_end_button):
            row.addWidget(w)
        row.addWidget(self.sec_label, 1)

        t = self.sections_table = QTableWidget(0, 9)
        t.setHorizontalHeaderLabels([tr("Frames"), tr("Frame rate"), tr("Speed"), tr("Length"),
                                     tr("Smooth in"), tr("Smooth out"), tr("Re-encode"),
                                     tr("Output fps"), ""])
        for col in (4, 5):
            t.horizontalHeaderItem(col).setToolTip(tr(
                "Smooth transition: the speed changes evenly over 0.5 s, centred on the border\n"
                "(e.g. from 9.6× slow motion to real time), instead of jumping."))
        t.horizontalHeaderItem(6).setToolTip(tr("Smart re-encode: re-encode this section (source "
                                                "codec) – everything else is copied."))
        t.horizontalHeaderItem(7).setToolTip(tr("Constant frame rate of the re-encoded section."))
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
        t.itemSelectionChanged.connect(self._selection_changed)
        t.hide()
        return row

    def _build_batch_row(self) -> QHBoxLayout:
        self.batch_button = QPushButton(tr("➕ Add to batch"))
        self.batch_button.setToolTip(tr(
            "Add this clip as it is now – processing mode, output settings, trim and speed\n"
            "sections – to the batch list (Export tab). The sections stay here, so you can add\n"
            "the same clip again, e.g. once lossless and once with smart re-encode."))
        self.batch_button.clicked.connect(lambda: self.clip and self.add_to_batch.emit(self.clip))
        self.update_button = QPushButton(tr("✔ Update batch entry"))
        self.update_button.setToolTip(tr("Replace the batch entry you opened with this clip as "
                                         "it is now"))
        self.update_button.clicked.connect(
            lambda: self.clip and self.update_entry.emit(self.clip))
        self.update_button.hide()
        self.clear_sections_button = QPushButton(tr("Clear sections"))
        self.clear_sections_button.setToolTip(tr("Remove all speed sections of this clip "
                                                 "(can be undone)"))
        self.clear_sections_button.clicked.connect(self._confirm_clear)
        self.undo_button = QPushButton(tr("↶ Undo"))
        self.undo_button.clicked.connect(self.undo)
        self.redo_button = QPushButton(tr("↷ Redo"))
        self.redo_button.clicked.connect(self.redo)
        row = QHBoxLayout()
        row.addWidget(self.batch_button)
        row.addWidget(self.update_button)
        row.addStretch(1)                # far from "Add to batch" – no accidental clicks
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)
        row.addWidget(self.clear_sections_button)
        return row

    def set_editing(self, label: str | None) -> None:
        """Show "Update batch entry" while a batch entry is open for editing (None = not)."""
        self.update_button.setVisible(label is not None)
        if label is not None:
            self.update_button.setToolTip(tr("Replace the batch entry “%s” with this clip "
                                             "as it is now", label))

    def _confirm_clear(self) -> None:
        if not self._ready() or not self.clip.segments:
            return
        n = len(self.clip.segments)
        answer = QMessageBox.question(
            self, tr("Clear sections"),
            trp("Remove all %d speed section of %s?\n\n"
                "You can bring them back with “↶ Undo” (Ctrl+Z).",
                "Remove all %d speed sections of %s?\n\n"
                "You can bring them back with “↶ Undo” (Ctrl+Z).", n, n, self.clip.path.name),
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Yes:
            self.clear_sections()

    def clear_sections(self) -> None:
        if not self._ready() or not self.clip.segments:
            return
        n = len(self.clip.segments)
        self.clip.edit_segments([], trp("clear %d section", "clear %d sections", n, n))
        self.timeline.pending = (None, None)
        self._sections_changed()

    def undo(self) -> None:
        if self.clip and (what := self.clip.undo()):
            self._sections_changed()
            self._note(tr("Undone: %s", what))

    def redo(self) -> None:
        if self.clip and (what := self.clip.redo()):
            self._sections_changed()
            self._note(tr("Redone: %s", what))

    def _note(self, text: str) -> None:
        self.sec_label.setText(text)

    def _set_magnetic(self, on: bool) -> None:
        self.timeline.magnetic = on
        QSettings().setValue("preview/magnetic", on)

    def _rate_items(self) -> list[tuple[str, str]]:
        """Slower rates (standard frame rates), the original, and speed-ups up to 8×."""
        real = self.clip.info.real_fps
        items = [(f"{label} – {fmt_slowdown(float(real / fps))}", str(fps))
                 for label, fps in frame_rate_choices(real) if fps <= real]
        items += [(tr("%s fps – %d× faster", fmt_rate(real * k), k), str(real * k))
                  for k in SPEEDUP_FACTORS]
        return items

    def section_start(self) -> None:
        if self._ready():
            self.timeline.pending = (self.clip.playhead, self.timeline.pending[1])
            self._sections_changed(emit=False)

    def section_end(self) -> None:
        if self._ready():
            start = self.timeline.pending[0]
            if start is None:           # right after the section before (or the trim start)
                start = seg.quick_start(self.clip.segments, self.clip.playhead, self.clip.trim.start)
            self.timeline.pending = (start, self.clip.playhead)
            self._sections_changed(emit=False)

    def add_section(self) -> None:
        a, b = self.timeline.pending
        if not self._ready() or a is None or b is None or self.sec_fps.currentData() is None:
            return
        new = seg.Segment(min(a, b), max(a, b) + 1, Fraction(self.sec_fps.currentData()),
                          out_fps=self._default_out_fps())
        self.clip.edit_segments(seg.add(self.clip.segments, new),
                                tr("add section %d–%d", new.start, new.end - 1))
        self.timeline.pending = (None, None)
        self._show_row = self.clip.segments.index(new)    # scroll the table to the new row
        self._sections_changed()

    def _default_out_fps(self) -> Fraction:
        return default_out_fps()

    def remove_section(self, index: int) -> None:
        s = self.clip.segments[index]
        self.clip.edit_segments(self.clip.segments[:index] + self.clip.segments[index + 1:],
                                tr("remove section %d–%d", s.start, s.end - 1))
        self._sections_changed()

    def _set_section_fps(self, index: int, value: str) -> None:
        self._set_section(index, fps=Fraction(value))

    def _set_section(self, index: int, **changes) -> None:
        if self.clip and index < len(self.clip.segments):
            if "out_fps" in changes:
                QSettings().setValue("sections/out_fps", str(changes["out_fps"]))
            elif changes.get("reencode") and self.clip.segments[index].out_fps is None:
                changes["out_fps"] = self._default_out_fps()
            s = self.clip.segments[index]
            new = list(self.clip.segments)
            new[index] = replace(s, **changes)
            self.clip.edit_segments(new, tr("change section %d–%d", s.start, s.end - 1))
            self._show_row = index            # keep the edited row in view
            self._sections_changed()

    def _seek_section(self, row: int) -> None:
        if self.clip and row < len(self.clip.segments):
            self.seek(self.clip.segments[row].start)

    def _select_section(self, index: int) -> None:
        """Timeline click: the section there becomes the one to edit (-1: none)."""
        self._selected = index if index >= 0 else None
        t = self.sections_table
        t.blockSignals(True)
        if index >= 0 and index < t.rowCount():
            t.selectRow(index)
            t.scrollTo(t.model().index(index, 0))
        else:
            t.clearSelection()
        t.blockSignals(False)
        self._update_selection_buttons()

    def _selection_changed(self) -> None:
        rows = {i.row() for i in self.sections_table.selectedIndexes()}
        self._selected = min(rows) if rows else None
        self._update_selection_buttons()

    def _update_selection_buttons(self) -> None:
        on = (self._ready() and self._selected is not None
              and self._selected < len(self.clip.segments))
        self.sel_start_button.setEnabled(on)
        self.sel_end_button.setEnabled(on)

    def _set_selected_range(self, start: bool) -> None:
        i = self._selected
        if not self._ready() or i is None or i >= len(self.clip.segments):
            return
        s, ph = self.clip.segments[i], self.clip.playhead
        a, b = (ph, s.end - 1) if start else (s.start, ph)
        a, b = min(a, b), max(a, b) + 1
        others = self.clip.segments[:i] + self.clip.segments[i + 1:]
        new = seg.add(others, replace(s, start=a, end=b))
        self.clip.edit_segments(new, tr("section now %d–%d", a, b - 1))
        self._selected = next((k for k, x in enumerate(new) if x.start == a), None)
        self._sections_changed()

    def _set_smooth(self, index: int, at_start: bool, on: bool) -> None:
        if not self._ready() or index >= len(self.clip.segments):
            return
        s = self.clip.segments[index]
        border = s.start if at_start else s.end
        self.clip.edit_segments(seg.with_smooth(self.clip.segments, border, on),
                                tr("smooth transition at frame %d on", border) if on
                                else tr("smooth transition at frame %d off", border))
        self._show_row = index
        self._sections_changed()

    # ------------------------------------------------------------------ dragging a border

    def _border_grabbed(self, border: int) -> None:
        if not self._ready():
            return
        self._stop_playback()
        self._drag_base = list(self.clip.segments)
        self._drag_from = border

    def _border_moved(self, to: int) -> None:
        if self._drag_base is None:
            return
        count = self.clip.frames.count
        lo, hi = seg.border_range(self._drag_base, self._drag_from, count)
        q = max(lo, min(to, hi))
        self.clip.segments[:] = seg.moved_border(self._drag_base, self._drag_from, q, count)
        self.timeline.dragged_border = q
        self.seek(min(q, count - 1))            # preview: the first frame after the border

    def _border_released(self) -> None:
        if self._drag_base is None:
            return
        moved = list(self.clip.segments)
        self.clip.segments[:] = self._drag_base     # the drag becomes one undo step
        q = next((b for b in seg.borders(moved, self.clip.frames.count)
                  if b not in seg.borders(self._drag_base, self.clip.frames.count)), None)
        self._drag_base = None
        self.clip.edit_segments(moved, tr("move border to frame %d", q) if q is not None
                                else tr("move border"))
        self._sections_changed()

    def sections_replaced(self) -> None:
        """The clip's sections (or trim) were replaced from outside, e.g. by loading a file."""
        self.timeline.pending = (None, None)
        self._sections_changed(emit=False)

    def _sections_changed(self, emit: bool = True) -> None:
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
        if self._selected is not None and (not clip or self._selected >= len(clip.segments)):
            self._selected = None
        self._update_selection_buttons()
        for button, steps, is_undo in ((self.undo_button, clip.undo_steps if clip else [], True),
                                       (self.redo_button, clip.redo_steps if clip else [], False)):
            button.setEnabled(bool(steps))
            text = tr("↶ Undo") if is_undo else tr("↷ Redo")
            button.setText(f"{text} ({len(steps)})" if steps else text)
            key = "Ctrl+Z" if is_undo else "Ctrl+Shift+Z / Ctrl+Y"
            n = len(steps)
            if not steps:
                tip = tr("Nothing to undo (%s)", key) if is_undo else tr("Nothing to redo (%s)", key)
            elif is_undo:
                tip = trp("Undo: %s (%s, %d step)", "Undo: %s (%s, %d steps)", n, steps[-1][0], key, n)
            else:
                tip = trp("Redo: %s (%s, %d step)", "Redo: %s (%s, %d steps)", n, steps[-1][0], key, n)
            button.setToolTip(tip)
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
            self.sec_label.setText(tr("Mark a range with [ and ] to play it at another frame rate.")
                                   if not clip.segments else "")
        elif b is None:
            self.sec_label.setText(tr("Section from frame %d – now set the end (])", a))
        else:
            lo, hi = min(a, b), max(a, b)
            self.sec_label.setText(tr("Frames %d–%d (%d) – choose the frame rate "
                                      "and click “Add section”", lo, hi, hi - lo + 1))

        t = self.sections_table
        t.setVisible(bool(clip.segments))
        smart_mode = clip.settings.smart
        t.setColumnHidden(6, not smart_mode)
        t.setColumnHidden(7, not smart_mode)
        t.setColumnHidden(4, easy_mode())       # Easy: every speed change is smoothed anyway
        t.setColumnHidden(5, easy_mode())
        key = (id(clip), tuple(clip.segments), tuple(items), smart_mode)
        if key == self._table_key:          # rebuild only on change (refresh runs on every seek)
            return
        self._table_key = key
        scroll = t.verticalScrollBar().value()      # a rebuild would jump to the top
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
            for col, at_start in ((4, True), (5, False)):
                other = seg.neighbour_rate(clip.segments, row, at_start, clip.frames.count,
                                           clip.info.real_fps)
                on = s.smooth_start if at_start else s.smooth_end
                smooth = QCheckBox()
                smooth.setChecked(on)
                smooth.setEnabled(on or (other is not None and other != s.fps))
                if other is None:
                    smooth.setToolTip(tr("The clip starts here") if at_start
                                      else tr("The clip ends here"))
                elif other == s.fps:
                    smooth.setToolTip(tr("Same speed on the other side"))
                else:
                    a, b = (other, s.fps) if at_start else (s.fps, other)
                    smooth.setToolTip(tr("%s → %s, changing evenly over 0.5 s",
                                         fmt_slowdown(float(clip.info.real_fps / a)),
                                         fmt_slowdown(float(clip.info.real_fps / b))))
                smooth.toggled.connect(lambda v, row=row, at_start=at_start: QTimer.singleShot(
                    0, lambda: self._set_smooth(row, at_start, v)))
                t.setCellWidget(row, col, _centered(smooth))
            check = QCheckBox()
            check.setChecked(s.reencode)
            check.setToolTip(tr("Re-encode this section with the source codec (smart re-encode)"))
            check.toggled.connect(lambda on, row=row: QTimer.singleShot(
                0, lambda: self._set_section(row, reencode=on)))
            t.setCellWidget(row, 6, _centered(check))
            out = QComboBox()
            for label, fps in formats.FRAME_RATES:
                out.addItem(f"{label} fps", str(fps))
            current = str(s.out_fps or self._default_out_fps())
            if out.findData(current) < 0:
                out.addItem(f"{fmt_rate(Fraction(current))} fps", current)
            out.setCurrentIndex(out.findData(current))
            out.setEnabled(s.reencode)
            out.activated.connect(lambda _, row=row, c=out: QTimer.singleShot(
                0, lambda: self._set_section(row, out_fps=Fraction(c.currentData()))))
            t.setCellWidget(row, 7, out)
            remove = QToolButton()
            remove.setText("✕")
            remove.setToolTip(tr("Remove this section"))
            remove.clicked.connect(lambda _=False, row=row: QTimer.singleShot(
                0, lambda: self.remove_section(row)))
            t.setCellWidget(row, 8, remove)
        t.verticalScrollBar().setValue(scroll)
        if self._selected is not None and self._selected < t.rowCount():
            t.blockSignals(True)
            t.selectRow(self._selected)
            t.blockSignals(False)
        if self._show_row is not None and self._show_row < t.rowCount():
            index = t.model().index(self._show_row, 0)
            t.scrollTo(index)
            QTimer.singleShot(0, lambda: t.scrollTo(index))   # again once the rows are laid out
        self._show_row = None

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
            self._play_note = tr("Playing speed sections at %s fps (%s in total)",
                                 fmt_rate(plan.fps), fmt_seconds(job.output_duration))
        else:
            self._play_note = tr("Playing at %s fps – %s", fmt_rate(job.settings.fps),
                                 fmt_slowdown(1 / float(job.speed)))
        if plan.note:
            self._play_note += f"  ·  {plan.note}"
        self.player.play(plan)
        self.play_button.setText(tr("■ Stop"))

    def _stop_playback(self) -> None:
        if self.player.playing:
            self.player.stop()
            self.fetcher.reset()     # the view shows a small playback frame – fetch again
            self.note.clear()
        self.play_button.setText(tr("▶ Play preview"))

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
            note += ("  ·  <span style='color:#d35400'>"
                     + tr("decoding can't keep up – the preview plays slower than the export will")
                     + "</span>")
        self.note.setText(note)

    def _play_finished(self, message: str) -> None:
        self._stop_playback()
        self.note.setText(tr("Preview failed: %s", message) if message else "")
        self.refresh()

    # ------------------------------------------------------------------ labels

    def _update_labels(self) -> None:
        clip, job = self.clip, self.clip.job
        fm, ph = clip.frames, clip.playhead
        t = fm.times[ph] - fm.times[0]
        text = (tr("Frame %d of %d", ph, fm.count - 1)
                + f"  ·  {fmt_duration(t)}{_key_text(fm, ph)}")
        if clip.proxy and not clip.proxy_done:
            ready = sum(1 for p in clip.proxy if p is not None) / len(clip.proxy)
            text += "  ·  " + tr("fast preview %.0f%%", ready * 100)
        start = clip.trim.start
        end = clip.trim.end if clip.trim.end is not None else fm.count
        if start <= ph < end:
            out_t = job.output_time(ph)
            text += "  ·  " + tr("output %s", fmt_duration(out_t))
        else:
            text += "  ·  " + tr("outside the trim range")
        self.position.setText(text)

        if start == 0 and end == fm.count:
            trim = trp("Whole clip: %d frame", "Whole clip: %d frames", fm.count, fm.count)
        else:
            trim = trp("In %d  ·  Out %d  ·  %d of %d frame", "In %d  ·  Out %d  ·  %d of %d frames",
                       fm.count, start, end - 1, end - start, fm.count)
        trim += "  →  " + trp("%d output frame, %s", "%d output frames, %s", job.output_frame_count,
                              job.output_frame_count, fmt_duration(job.output_duration))
        self.trim_label.setText(trim)
        self.snap_button.setVisible(job.snaps_to_keyframes and not job.trim_on_keyframes())
        self.key_hint.setVisible(job.snaps_to_keyframes)
        if job.mode == Mode.SMART:
            self.key_hint.setText(tr(
                "🔑 Smart re-encode joins copied and re-encoded parts only at keyframes (here "
                "every %d frames): in / out points snap to them, and "
                "sections marked “Re-encode” are widened to the nearest keyframes – the extra "
                "frames are re-encoded at the speed they have anyway.", _key_interval(job.frames)))
        elif job.snaps_to_keyframes:
            self.key_hint.setText(tr(
                "🔑 Lossless mode: in / out points can only be set at keyframes (here every "
                "%d frames). Only keyframes are complete pictures – all other "
                "frames depend on the frames before them, so a cut elsewhere would need "
                "re-encoding. Choose a codec for frame-exact cuts. (Speed sections are not "
                "cuts – they can start at any frame.)", _key_interval(job.frames)))


def default_out_fps() -> Fraction:
    """The output frame rate chosen last – the default for further (smart) sections."""
    value = QSettings().value("sections/out_fps", "")
    try:
        return Fraction(str(value)) if value else smart.DEFAULT_OUT_FPS
    except (ValueError, ZeroDivisionError):
        return smart.DEFAULT_OUT_FPS


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
    return "  · " + tr("keyframe") if fm.keyframe_at_or_before(frame) == frame else ""


def transport_icon_size(kind: str) -> QSize:
    return QSize(28, 20) if kind.startswith("key") else QSize(20, 20)


def transport_icon(kind: str, color: QColor) -> QIcon:
    """Transport symbols on a 24-unit grid (28 wide for the key buttons), the same shapes as the
    Android app: |◀ and ▶| with the bar centred on the triangle; "− key" and "key +" close
    together (sign drawn as bars, not a font glyph)."""
    wide = kind.startswith("key")
    w = 28 if wide else 24
    pix = QPixmap(w * 4, 24 * 4)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(4, 4)
    p.setPen(Qt.NoPen)
    p.setBrush(color)

    def key(dx: float) -> None:
        ring = QPainterPath()
        ring.setFillRule(Qt.OddEvenFill)
        ring.addEllipse(QPointF(7 + dx, 12), 4.5, 4.5)
        ring.addEllipse(QPointF(7 + dx, 12), 2, 2)
        p.drawPath(ring)
        for x, y, rw, rh in ((11, 10.9, 11, 2.2), (18.5, 13, 2.2, 3.5), (15, 13, 2.2, 2.5)):
            p.drawRect(QRectF(x + dx, y, rw, rh))

    if kind == "key-":
        p.drawRect(QRectF(1, 10.9, 5.5, 2.2))
        key(5)
    elif kind == "key+":
        key(-2)
        p.drawRect(QRectF(21.5, 10.9, 5.5, 2.2))
        p.drawRect(QRectF(23.15, 9.25, 2.2, 5.5))
    elif kind == "first":
        p.drawRect(QRectF(5, 6, 2.4, 12))
        p.drawPolygon([QPointF(19, 6), QPointF(19, 18), QPointF(8.5, 12)])
    else:   # last
        p.drawRect(QRectF(16.6, 6, 2.4, 12))
        p.drawPolygon([QPointF(5, 6), QPointF(5, 18), QPointF(15.5, 12)])
    p.end()
    return QIcon(pix)
