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
from . import workers

COMPARE_MODES = (("side", "Side by side"), ("wipe", "Wipe (drag the line)"),
                 ("source", "Source only"), ("output", "Output only"))


def _fit(img_w: int, img_h: int, box: QRectF) -> QRectF:
    f = min(box.width() / img_w, box.height() / img_h)
    w, h = img_w * f, img_h * f
    return QRectF(box.x() + (box.width() - w) / 2, box.y() + (box.height() - h) / 2, w, h)


class CompareView(QWidget):
    """Paints the source and the output frame side by side or with a wipe line."""
    resized = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "side"
        self.source = None
        self.output = None
        self.out_size: tuple[int, int] | None = None   # output frame size (for the wipe box)
        self.wipe = 0.5
        self.message = ""
        self.setMinimumSize(200, 120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()
        self.resized.emit()     # the wanted image size changes

    def image_boxes(self) -> tuple[QRectF, QRectF]:
        """Boxes (in widget pixels) for the source and the output picture."""
        r = QRectF(self.rect()).adjusted(4, 4, -4, -22)
        if self.mode == "side":
            half = (r.width() - 6) / 2
            return QRectF(r.x(), r.y(), half, r.height()), QRectF(r.x() + half + 6, r.y(), half, r.height())
        if self.mode == "wipe" and self.out_size:
            box = _fit(*self.out_size, r)
            return box, box
        return r, r

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111"))
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.message:
            p.setPen(QColor("#999"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.message)
            return
        src_box, out_box = self.image_boxes()
        label_font = QFont(self.font())
        label_font.setPointSizeF(label_font.pointSizeF() * 0.9)
        p.setFont(label_font)

        def draw(img, box, clip_rect=None):
            if img is None or img.isNull():
                return
            target = _fit(img.width(), img.height(), box)
            p.save()
            if clip_rect is not None:
                p.setClipRect(clip_rect)
            p.drawImage(target, img)
            p.restore()

        h = self.height()
        if self.mode == "side":
            draw(self.source, src_box)
            draw(self.output, out_box)
            self._label(p, src_box, "Source")
            self._label(p, out_box, "Output")
        elif self.mode == "source":
            draw(self.source, src_box)
            self._label(p, src_box, "Source")
        elif self.mode == "output":
            draw(self.output, out_box)
            self._label(p, out_box, "Output")
        else:
            x = out_box.x() + self.wipe * out_box.width()
            draw(self.source, out_box, QRectF(0, 0, x, h))
            draw(self.output, out_box, QRectF(x, 0, self.width() - x, h))
            p.setPen(QPen(QColor("#f1c40f"), 2))
            p.drawLine(QPointF(x, out_box.top()), QPointF(x, out_box.bottom()))
            p.setPen(QColor("#ccc"))
            p.drawText(QRectF(out_box.x(), out_box.bottom() + 2, x - out_box.x() - 6, 18),
                       Qt.AlignRight | Qt.AlignVCenter, "◀ Source")
            p.drawText(QRectF(x + 6, out_box.bottom() + 2, out_box.right() - x, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, "Output ▶")

    @staticmethod
    def _label(p: QPainter, box: QRectF, text: str) -> None:
        p.setPen(QColor("#ccc"))
        p.drawText(QRectF(box.x(), box.bottom() + 2, box.width(), 18), Qt.AlignCenter, text)

    def _set_wipe(self, x: float) -> None:
        box = self.image_boxes()[1]
        self.wipe = min(1.0, max(0.0, (x - box.x()) / max(1.0, box.width())))
        self.update()

    def mousePressEvent(self, event) -> None:
        if self.mode == "wipe":
            self._set_wipe(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        if self.mode == "wipe" and event.buttons() & Qt.LeftButton:
            self._set_wipe(event.position().x())

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
        self.frames_spin.setSuffix(" frames")
        self.frames_spin.setMaximumWidth(130)
        self.frames_spin.setToolTip("Number of output frames to encode, starting at the playhead.")
        self.run_button = QPushButton("Run test encode")
        self.run_button.setToolTip("Encodes the frames from the playhead (see the Preview tab)\n"
                                   "with exactly the current output settings.")
        self.run_button.clicked.connect(lambda: self.start_test.emit(self.frames_spin.value()))
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_test)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        top = QHBoxLayout()
        for w in (QLabel("Test:"), self.frames_spin, self.run_button, self.cancel_button):
            top.addWidget(w)
        top.addWidget(self.progress, 3)
        top.addStretch(1)

        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setTextFormat(Qt.RichText)

        self.view = CompareView()
        self.mode_combo = QComboBox()
        for key, label in COMPARE_MODES:
            self.mode_combo.addItem(label, key)
        self.mode_combo.currentIndexChanged.connect(
            lambda: self.view.set_mode(self.mode_combo.currentData()))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._request_frames)
        self.slider.setToolTip("Frame of the test output")
        self.frame_label = QLabel()
        compare = QHBoxLayout()
        compare.addWidget(self.mode_combo)
        compare.addWidget(self.slider, 1)
        compare.addWidget(self.frame_label)

        self.cmd_button = QToolButton()
        self.cmd_button.setText("FFmpeg command ▸")
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
        self.cmd_button.setText("FFmpeg command ▾" if on else "FFmpeg command ▸")

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
        eta = f", {fmt_seconds(p.eta)} left" if p.eta is not None else ""
        self.progress.setFormat(f"{p.frame}/{p.total_frames} frames, {p.fps:.1f} fps{eta}")

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
            self.run_button.setText(f"Run test encode from frame {clip.playhead}")
        else:
            self.run_button.setText("Run test encode")

        test = clip.test if clip else None
        self.result.setText(self._result_text(clip) if clip else "")
        if test and test.args:
            self.cmd.setPlainText(" ".join(_quote(a) for a in test.args))
        else:
            self.cmd.clear()

        media = clip.test_media if clip else None
        has_media = bool(media and media.frames.count)
        self.slider.setEnabled(has_media)
        self.mode_combo.setEnabled(has_media)
        if has_media:
            self.slider.setRange(0, media.frames.count - 1)
            self.view.out_size = media.info.display_size
            self.view.message = ""
        else:
            self.view.message = ("Run a test encode to compare source and output."
                                 if not (test and test.ok) else
                                 "No comparison for this output format.")
            self.frame_label.clear()
        self.view.update()
        self._request_frames()

    # ------------------------------------------------------------------ text

    def _result_text(self, clip: Clip) -> str:
        test = clip.test
        if clip.testing:
            return "Encoding test frames…"
        if test is None:
            return ("Encodes a short piece with exactly the current settings and measures the "
                    "speed. That gives the time estimate for the clip and the whole batch.")
        if test.cancelled:
            return "Test cancelled."
        if not test.ok:
            return f"<span style='color:#c0392b'>Test failed:</span> {_html(test.error[-600:])}"
        job = clip.job
        lines = [f"<b>{test.frames} frames in {test.elapsed:.1f} s → {test.fps:.1f} frames/s</b>,"
                 f" {fmt_bytes(test.bytes)}"]
        if test.settings == clip.settings:
            est = testencode.estimate(job, test, [])
            whole = "trimmed clip" if clip.trim.start or clip.trim.end is not None else "whole clip"
            lines.append(f"Estimate for the {whole} ({job.output_frame_count} frames, "
                         f"{fmt_duration(job.output_duration)}): <b>{fmt_seconds(est.seconds)}</b>, "
                         f"about <b>{fmt_bytes(est.bytes)}</b>")
            lines.append("<small>Accuracy depends on how typical the test piece is: test at "
                         "a busy part of the clip for a safe estimate.</small>")
            if job.mode == Mode.RETIME:
                lines.append("Lossless retime copies the stream – no encoding, so it is fast "
                             "for any length.")
        else:
            lines.append("<span style='color:#d35400'>The output settings changed after this "
                         "test – the estimate no longer applies. Run the test again.</span>")
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
        self.frame_label.setText(f"output {k + 1}/{media.frames.count} ↔ source frame {src}")
        dpr = self.devicePixelRatioF()
        src_box, out_box = self.view.image_boxes()

        def size(info, box):
            return preview.fit_size(info, max(16, int(box.width() * dpr)),
                                    max(16, int(box.height() * dpr)))
        if self.view.mode == "wipe":   # both pictures fill the same box
            box = out_box
            self.src_fetch.request(clip, src, size(clip.info, box))
            self.out_fetch.request(media, k, size(media.info, box))
        else:
            self.src_fetch.request(clip, src, size(clip.info, src_box))
            self.out_fetch.request(media, k, size(media.info, out_box))


def _quote(arg: str) -> str:
    return f'"{arg}"' if any(c in arg for c in " ;()[]'") else arg


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")

