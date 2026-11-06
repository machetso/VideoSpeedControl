# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Read-only details of the selected clip."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..core import formats
from ..i18n import N_, tr, trp
from .clips import Clip, Status, chroma_label, fmt_duration, fmt_rate, fmt_slowdown

FIELDS = (N_("File"), N_("Device"), N_("Recorded"), N_("Container"), N_("Codec"), N_("Size"),
          N_("Frame rate"), N_("Frames"), N_("Duration"), N_("Keyframes"), N_("Pixel format"),
          N_("Colour"), N_("Bitrate"), N_("Audio"), N_("Other streams"))


def _not_stored() -> str:
    return f"<span style='color:gray'>{tr('not stored in the file')}</span>"


class InfoPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__(tr("Clip info"), parent)
        self.values: dict[str, QLabel] = {}
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for name in FIELDS:
            label = QLabel()
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            self.values[name] = label
            form.addRow(tr("%s:", tr(name)), label)

        self.speeds = QLabel()
        self.speeds.setToolTip(tr("Speed at which every source frame is used exactly once.\n"
                                  "Only these speeds allow lossless retiming (mode A)."))
        form.addRow(tr("Lossless speed:"), self.speeds)

        self.message = QLabel(tr("Add clips with “Add files…” or drag & drop."))
        self.message.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(form_widget)
        layout = QVBoxLayout(self)
        layout.addWidget(self.message)
        layout.addWidget(scroll)
        self.show_clip(None)

    def show_clip(self, clip: Clip | None) -> None:
        i = clip.info if clip else None
        if clip is None:
            self.message.setText(tr("Add clips with “Add files…” or drag & drop."))
        elif clip.status == Status.ERROR:
            self.message.setText(tr("<b>%s</b> cannot be used:<br>%s", clip.path.name, clip.error))
        else:
            self.message.setText(tr(clip.status.value) if clip.status != Status.READY else "")
        self.message.setVisible(bool(self.message.text()))
        if i is None:
            for label in self.values.values():
                label.clear()
            self.speeds.clear()
            return

        fm = clip.frames
        w, h = i.display_size
        size = f"{i.width}×{i.height}"
        if (w, h) != (i.width, i.height):
            size += tr(" → displayed %d×%d", w, h)
        if i.sar != 1:
            size += f"  (SAR {i.sar.numerator}:{i.sar.denominator})"
        if i.rotation:
            size += tr("  rotated %d°", i.rotation)
        aspect = i.display_aspect
        size += f"  DAR {aspect.numerator}:{aspect.denominator}"

        rate = f"{fmt_rate(i.fps)} fps"
        if i.avg_fps and i.avg_fps != i.fps:
            rate += tr(" (average %s)", fmt_rate(i.avg_fps))
        vfr = i.possibly_vfr
        if fm:
            lo, hi = fm.frame_intervals()
            vfr = vfr or hi > lo * 1.5
        rate += ("  <span style='color:#d35400'>" + tr("⚠ possibly variable frame rate") + "</span>"
                 if vfr else "  " + tr("constant"))
        if i.slowmo_factor:
            rate += "<br>" + slowmo_note(i)

        if fm:
            gop = (fm.keyframes[1] - fm.keyframes[0]) if len(fm.keyframes) > 1 else fm.count
            keys = trp("%d (every ≈ %d frame)", "%d (every ≈ %d frames)", gop, len(fm.keyframes), gop)
        else:
            keys = tr("scanning…")
        bitrate = i.stream_bitrate or i.bitrate
        values = {
            "File": f"{i.path.name}  ({i.size_bytes / 1e6:.1f} MB)",
            "Device": i.device or _not_stored(),
            "Recorded": i.recorded.strftime("%Y-%m-%d %H:%M:%S") if i.recorded else _not_stored(),
            "Container": i.container_long or i.container,
            "Codec": f"{i.codec}{' ' + i.profile if i.profile else ''} – {i.codec_long}",
            "Size": size,
            "Frame rate": rate,
            "Frames": str(fm.count if fm else i.frame_count),
            "Duration": fmt_duration(i.duration),
            "Keyframes": keys,
            "Pixel format": tr("%s – %s, %d-bit", i.pix_fmt, chroma_label(i.chroma), i.bit_depth),
            "Colour": tr("%s; space %s, primaries %s, range %s", i.transfer_label,
                         i.color_space or "?", i.color_primaries or "?", i.color_range or "?"),
            "Bitrate": f"{bitrate / 1e6:.1f} Mbit/s" if bitrate else tr("unknown"),
            "Audio": tr("%s  (exported, pitch preserved – see Audio in the output settings)",
                        i.audio) if i.audio else tr("none"),
            "Other streams": tr("%s  (only the first audio track is exported)",
                                ", ".join(i.extra_streams)) if i.extra_streams else "–",
        }
        for name, text in values.items():
            self.values[name].setText(text)

        rows = "".join(
            f"<tr><td>{label.split()[0]}&nbsp;fps</td><td align=right>&nbsp;{float(fps / i.real_fps):.4f}×</td>"
            f"<td align=right>&nbsp;({fmt_slowdown(float(i.real_fps / fps))})</td></tr>"
            for label, fps in formats.FRAME_RATES)
        self.speeds.setText(f"<table cellspacing=0>{rows}</table>")


def slowmo_note(i) -> str:
    """Phone slow motion: the file plays slower than it was recorded."""
    return ("<span style='color:#d35400'>"
            + tr("Phone slow-mo: recorded at %s fps, the file plays at %s fps (%s× slower).",
                 fmt_rate(i.capture_fps), fmt_rate(i.fps), f"{i.slowmo_factor:.3g}")
            + "</span><br>"
            + tr("The app uses %s fps as the original: speeds and “× slower” refer to real time.",
                 fmt_rate(i.capture_fps)))
