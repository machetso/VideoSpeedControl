# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Test encode of N frames from the playhead and a source / output comparison."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
                               QPushButton, QSizePolicy, QSlider, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from ..core import preview, testencode
from ..core.job import Mode
from .clips import Clip, Status, fmt_bytes, fmt_duration, fmt_seconds
from ..i18n import N_, tr, trp
from . import workers
from .zoom import ZoomState, fit_rect

COMPARE_MODES = (("side", N_("Side by side")), ("wipe", N_("Wipe (drag the line)")),
                 ("source", N_("Source only")), ("output", N_("Output only")))


class CompareView(QWidget):
    """Paints the source and the output frame side by side or with a wipe line.

    Both pictures share one zoom / pan state and are laid out in the output's geometry, so
    the same region is always shown; the source is fitted inside the output frame (which
    matches "fit (black bars)" exactly).
    """
    resized = Signal()

    def __init__(self, zoom: ZoomState, parent=None):
        super().__init__(parent)
        self.zoom = zoom
        self.zoom.changed.connect(self.update)
        self.mode = "side"
        self.source = None
        self.output = None
        self.src_size: tuple[int, int] | None = None   # native sizes
        self.out_size: tuple[int, int] | None = None
        self.wipe = 0.5
        self.message = ""
        self._drag: str | None = None
        self._last: QPointF | None = None
        self.setMinimumSize(200, 120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()
        self.resized.emit()     # the wanted image size changes

    def _boxes(self) -> tuple[QRectF, QRectF]:
        r = QRectF(self.rect()).adjusted(4, 4, -4, -22)
        if self.mode == "side":
            half = (r.width() - 6) / 2
            return (QRectF(r.x(), r.y(), half, r.height()),
                    QRectF(r.x() + half + 6, r.y(), half, r.height()))
        return r, r

    def frame_rects(self) -> tuple[QRectF, QRectF]:
        """Drawn rectangles of the source and the output picture."""
        dpr = self.devicePixelRatioF()
        src_box, out_box = self._boxes()
        if self.mode == "source" or not self.out_size:
            src = self.zoom.rect(*(self.src_size or (16, 9)), src_box, dpr)
            return src, src
        out = self.zoom.rect(*self.out_size, out_box, dpr)
        frame = out if self.mode != "side" else self.zoom.rect(*self.out_size, src_box, dpr)
        src = fit_rect(*self.src_size, frame) if self.src_size else frame
        return src, out

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111"))
        p.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom.zoom is None)
        if self.message:
            p.setPen(QColor("#999"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.message)
            return
        src_box, out_box = self._boxes()
        src_rect, out_rect = self.frame_rects()
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 0.9)
        p.setFont(font)

        def draw(img, rect, clip_box):
            if img is not None and not img.isNull():
                p.save()
                p.setClipRect(clip_box)
                p.drawImage(rect, img)
                p.restore()

        if self.mode == "side":
            draw(self.source, src_rect, src_box)
            draw(self.output, out_rect, out_box)
            self._label(p, src_box, tr("Source"))
            self._label(p, out_box, tr("Output"))
        elif self.mode == "source":
            draw(self.source, src_rect, src_box)
            self._label(p, src_box, tr("Source"))
        elif self.mode == "output":
            draw(self.output, out_rect, out_box)
            self._label(p, out_box, tr("Output"))
        else:
            x = self._wipe_x()
            left = QRectF(out_box.x(), out_box.y(), x - out_box.x(), out_box.height())
            right = QRectF(x, out_box.y(), out_box.right() - x, out_box.height())
            draw(self.source, src_rect, left)
            draw(self.output, out_rect, right)
            p.setPen(QPen(QColor("#f1c40f"), 2))
            p.drawLine(QPointF(x, out_box.top()), QPointF(x, out_box.bottom()))
            p.setPen(QColor("#ccc"))
            p.drawText(QRectF(out_box.x(), out_box.bottom() + 2, x - out_box.x() - 6, 18),
                       Qt.AlignRight | Qt.AlignVCenter, tr("◀ Source"))
            p.drawText(QRectF(x + 6, out_box.bottom() + 2, out_box.right() - x, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, tr("Output ▶"))

    @staticmethod
    def _label(p: QPainter, box: QRectF, text: str) -> None:
        p.setPen(QColor("#ccc"))
        p.drawText(QRectF(box.x(), box.bottom() + 2, box.width(), 18), Qt.AlignCenter, text)

    # ------------------------------------------------------------------ mouse

    def _wipe_x(self) -> float:
        box = self._boxes()[1]
        return box.x() + self.wipe * box.width()

    def _set_wipe(self, x: float) -> None:
        box = self._boxes()[1]
        self.wipe = min(1.0, max(0.0, (x - box.x()) / max(1.0, box.width())))
        self.update()

    def mousePressEvent(self, event) -> None:
        x = event.position().x()
        if self.mode == "wipe" and (self.zoom.zoom is None or abs(x - self._wipe_x()) < 8):
            self._drag = "wipe"
            self._set_wipe(x)
        elif self.zoom.zoom is not None:
            self._drag, self._last = "pan", event.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag == "wipe":
            self._set_wipe(event.position().x())
        elif self._drag == "pan":
            native = self.src_size if self.mode == "source" else self.out_size
            if native:
                self.zoom.pan(event.position() - self._last, *native, self.devicePixelRatioF())
            self._last = event.position()
        elif self.mode == "wipe":
            near = abs(event.position().x() - self._wipe_x()) < 8
            self.setCursor(Qt.SizeHorCursor if near else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.message:
            return
        src, out = self.frame_rects()
        pos = event.position()
        rect = src if self.mode == "source" or (self.mode == "side" and pos.x() < out.x()) else out
        if self.mode == "side" and rect is src and self.out_size:
            # the click was in the left half: map it into the output frame's geometry
            rect = self.zoom.rect(*self.out_size, self._boxes()[0], self.devicePixelRatioF())
        self.zoom.toggle_at(pos, rect)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class TestPanel(QWidget):
    start_test = Signal(int)     # number of output frames
    cancel_test = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip: Clip | None = None
        self.encoders = None

        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(5, 5000)
        self.frames_spin.setValue(testencode.DEFAULT_FRAMES)
        self.frames_spin.setSuffix(tr(" frames"))
        self.frames_spin.setMaximumWidth(130)
        self.frames_spin.setToolTip(tr("Number of output frames to encode, starting at the playhead."))
        self.run_button = QPushButton(tr("Run test encode"))
        self.run_button.setToolTip(tr("Encodes the frames from the playhead (see the Preview tab)\n"
                                      "with exactly the current output settings."))
        self.run_button.clicked.connect(lambda: self.start_test.emit(self.frames_spin.value()))
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.clicked.connect(self.cancel_test)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        top = QHBoxLayout()
        for w in (QLabel(tr("Test:")), self.frames_spin, self.run_button, self.cancel_button):
            top.addWidget(w)
        top.addWidget(self.progress, 3)
        top.addStretch(1)

        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setTextFormat(Qt.RichText)

        self.zoom = ZoomState(self)
        self.view = CompareView(self.zoom)
        self.zoom.changed.connect(self._request_frames)
        self.mode_combo = QComboBox()
        for key, label in COMPARE_MODES:
            self.mode_combo.addItem(tr(label), key)
        self.mode_combo.currentIndexChanged.connect(
            lambda: self.view.set_mode(self.mode_combo.currentData()))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._request_frames)
        self.slider.setToolTip(tr("Frame of the test output"))
        self.frame_label = QLabel()
        compare = QHBoxLayout()
        compare.addWidget(self.mode_combo)
        compare.addWidget(self.slider, 1)
        compare.addWidget(self.frame_label)
        compare.addWidget(self.zoom.combo())

        self.cmd_button = QToolButton()
        self.cmd_button.setText(tr("FFmpeg command ▸"))
        self.cmd_button.setCheckable(True)
        self.cmd_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.cmd = QPlainTextEdit()
        self.cmd.setReadOnly(True)
        self.cmd.setMaximumHeight(70)
        self.cmd.hide()
        self.cmd_button.toggled.connect(self._toggle_cmd)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.result)
        layout.addWidget(self.view, 1)
        layout.addLayout(compare)
        layout.addWidget(self.cmd_button)
        layout.addWidget(self.cmd)

        self.src_fetch = workers.FrameFetcher(self)
        self.out_fetch = workers.FrameFetcher(self)
        self.src_fetch.ready.connect(lambda img: self._image("source", img))
        self.out_fetch.ready.connect(lambda img: self._image("output", img))
        self._resize_timer = QTimer(self, singleShot=True, interval=150,
                                    timeout=self._request_frames)
        self.view.resized.connect(self._resize_timer.start)
        self.set_clip(None)

    def _toggle_cmd(self, on: bool) -> None:
        self.cmd.setVisible(on)
        self.cmd_button.setText(tr("FFmpeg command ▾") if on else tr("FFmpeg command ▸"))

    # ------------------------------------------------------------------ public

    def set_clip(self, clip: Clip | None) -> None:
        if clip is not self.clip:
            self.src_fetch.reset()
            self.out_fetch.reset()
            self.view.source = self.view.output = None
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
        self.clip = clip
        self.refresh()

    def set_progress(self, p) -> None:
        self.progress.setMaximum(max(1, p.total_frames))
        self.progress.setValue(min(p.frame, p.total_frames))
        eta = tr(", %s left", fmt_seconds(p.eta)) if p.eta is not None else ""
        self.progress.setFormat(trp("%d/%d frame, %.1f fps", "%d/%d frames, %.1f fps",
                                    p.total_frames, p.frame, p.total_frames, p.fps) + eta)

    def refresh(self) -> None:
        clip = self.clip
        ready = bool(clip and clip.frames and clip.status == Status.READY)
        testing = bool(clip and clip.testing)
        self.run_button.setEnabled(ready and not testing)
        self.frames_spin.setEnabled(ready and not testing)
        self.cancel_button.setVisible(testing)
        self.progress.setVisible(testing)
        if not testing:
            self.progress.reset()
        if clip and ready:
            self.run_button.setText(tr("Run test encode from frame %d", clip.playhead))
        else:
            self.run_button.setText(tr("Run test encode"))

        test = clip.test if clip else None
        self.result.setText(self._result_text(clip) if clip else "")
        if test and test.commands:
            self.cmd.setPlainText("\n\n".join(" ".join(_quote(a) for a in cmd)
                                                for cmd in test.commands))
        else:
            self.cmd.clear()

        media = clip.test_media if clip else None
        has_media = bool(media and media.frames.count)
        self.slider.setEnabled(has_media)
        self.mode_combo.setEnabled(has_media)
        if has_media:
            self.slider.setRange(0, media.frames.count - 1)
            self.view.out_size = media.info.display_size
            self.view.src_size = clip.info.display_size
            self.view.message = ""
        else:
            self.view.message = (tr("Run a test encode to compare source and output.")
                                 if not (test and test.ok) else
                                 tr("No comparison for this output format."))
            self.frame_label.clear()
        self.view.update()
        self._request_frames()

    # ------------------------------------------------------------------ text

    def _result_text(self, clip: Clip) -> str:
        test = clip.test
        if clip.testing:
            return tr("Encoding test frames…")
        if test is None:
            return tr("Encodes a short piece with exactly the current settings and measures the "
                      "speed. That gives the time estimate for the clip and the whole batch.")
        if test.cancelled:
            return tr("Test cancelled.")
        if not test.ok:
            return (f"<span style='color:#c0392b'>{tr('Test failed:')}</span> "
                    f"{_html(test.error[-600:])}")
        job = clip.job
        lines = ["<b>" + trp("%d frame in %.1f s → %.1f frames/s",
                             "%d frames in %.1f s → %.1f frames/s",
                             test.frames, test.frames, test.elapsed, test.fps)
                 + f"</b>, {fmt_bytes(test.bytes)}"]
        if test.settings == clip.settings:
            est = testencode.estimate(job, test, [])
            n = job.output_frame_count
            args = (n, fmt_duration(job.output_duration), fmt_seconds(est.seconds),
                    fmt_bytes(est.bytes))
            if clip.trim.start or clip.trim.end is not None:
                lines.append(trp("Estimate for the trimmed clip (%d frame, %s): <b>%s</b>, "
                                 "about <b>%s</b>",
                                 "Estimate for the trimmed clip (%d frames, %s): <b>%s</b>, "
                                 "about <b>%s</b>", n, *args))
            else:
                lines.append(trp("Estimate for the whole clip (%d frame, %s): <b>%s</b>, "
                                 "about <b>%s</b>",
                                 "Estimate for the whole clip (%d frames, %s): <b>%s</b>, "
                                 "about <b>%s</b>", n, *args))
            lines.append("<small>" + tr("Accuracy depends on how typical the test piece is: "
                                        "test at a busy part of the clip for a safe estimate.")
                         + "</small>")
            if job.mode == Mode.RETIME:
                lines.append(tr("Lossless retime copies the stream – no encoding, so it is fast "
                                "for any length."))
        else:
            lines.append("<span style='color:#d35400'>" + tr(
                "The output settings changed after this test – the estimate no longer applies. "
                "Run the test again.") + "</span>")
        return "<br>".join(lines)

    # ------------------------------------------------------------------ comparison

    def _image(self, which: str, image) -> None:
        setattr(self.view, which, image)
        self.view.update()

    def _request_frames(self) -> None:
        clip = self.clip
        media = clip.test_media if clip else None
        if not media or not media.frames.count or not clip.frames:
            return
        k = self.slider.value()
        test = clip.test
        src = min(test.source_frame(k), clip.frames.count - 1)
        self.frame_label.setText(tr("output %d/%d ↔ source frame %d", k + 1, media.frames.count,
                                     src))
        dpr = self.devicePixelRatioF()
        src_rect, out_rect = self.view.frame_rects()

        def size(info, rect):   # what is drawn, in device pixels – never more than the footage
            return preview.fit_size(info, max(16, int(rect.width() * dpr)),
                                    max(16, int(rect.height() * dpr)))
        self.src_fetch.request(clip, src, size(clip.info, src_rect))
        self.out_fetch.request(media, k, size(media.info, out_rect))


def _quote(arg: str) -> str:
    return f'"{arg}"' if any(c in arg for c in " ;()[]'") else arg


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")

