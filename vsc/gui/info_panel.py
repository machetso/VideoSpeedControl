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
from .clips import Clip, Status, chroma_label, fmt_duration, fmt_rate, fmt_slowdown

FIELDS = ("File", "Device", "Recorded", "Container", "Codec", "Size", "Frame rate", "Frames",
          "Duration", "Keyframes", "Pixel format", "Colour", "Bitrate", "Audio", "Other streams")
NOT_STORED = "<span style='color:gray'>not stored in the file</span>"


class InfoPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Clip info", parent)
        self.values: dict[str, QLabel] = {}
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for name in FIELDS:
            label = QLabel()
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            self.values[name] = label
            form.addRow(name + ":", label)

        self.speeds = QLabel()
        self.speeds.setToolTip("Speed at which every source frame is used exactly once.\n"
                               "Only these speeds allow lossless retiming (mode A).")
        form.addRow("Lossless speed:", self.speeds)

        self.message = QLabel("Add clips with “Add files…” or drag & drop.")
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
            self.message.setText("Add clips with “Add files…” or drag & drop.")
        elif clip.status == Status.ERROR:
            self.message.setText(f"<b>{clip.path.name}</b> cannot be used:<br>{clip.error}")
        else:
            self.message.setText(clip.status.value if clip.status != Status.READY else "")
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
            size += f" → displayed {w}×{h}"
        if i.sar != 1:
            size += f"  (SAR {i.sar.numerator}:{i.sar.denominator})"
        if i.rotation:
            size += f"  rotated {i.rotation}°"
        aspect = i.display_aspect
        size += f"  DAR {aspect.numerator}:{aspect.denominator}"

        rate = f"{fmt_rate(i.fps)} fps"
        if i.avg_fps and i.avg_fps != i.fps:
            rate += f" (average {fmt_rate(i.avg_fps)})"
        vfr = i.possibly_vfr
        if fm:
            lo, hi = fm.frame_intervals()
            vfr = vfr or hi > lo * 1.5
        rate += ("  <span style='color:#d35400'>⚠ possibly variable frame rate</span>"
                 if vfr else "  constant")
        if i.slowmo_factor:
            rate += "<br>" + slowmo_note(i)

        if fm:
            gop = (fm.keyframes[1] - fm.keyframes[0]) if len(fm.keyframes) > 1 else fm.count
            keys = f"{len(fm.keyframes)} (every ≈ {gop} frames)"
        else:
            keys = "scanning…"
        bitrate = i.stream_bitrate or i.bitrate
        values = {
            "File": f"{i.path.name}  ({i.size_bytes / 1e6:.1f} MB)",
            "Device": i.device or NOT_STORED,
            "Recorded": i.recorded.strftime("%Y-%m-%d %H:%M:%S") if i.recorded else NOT_STORED,
            "Container": i.container_long or i.container,
            "Codec": f"{i.codec}{' ' + i.profile if i.profile else ''} – {i.codec_long}",
            "Size": size,
            "Frame rate": rate,
            "Frames": str(fm.count if fm else i.frame_count),
            "Duration": fmt_duration(i.duration),
            "Keyframes": keys,
            "Pixel format": f"{i.pix_fmt} – {chroma_label(i.chroma)}, {i.bit_depth}-bit",
            "Colour": f"{i.transfer_label}; space {i.color_space or '?'}, "
                      f"primaries {i.color_primaries or '?'}, range {i.color_range or '?'}",
            "Bitrate": f"{bitrate / 1e6:.1f} Mbit/s" if bitrate else "unknown",
            "Audio": f"{i.audio}  (exported, pitch preserved – see Audio in the output settings)"
                     if i.audio else "none",
            "Other streams": ", ".join(i.extra_streams) + "  (only the first audio track is "
                             "exported)" if i.extra_streams else "–",
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
    return (f"<span style='color:#d35400'>Phone slow-mo: recorded at {fmt_rate(i.capture_fps)} "
            f"fps, the file plays at {fmt_rate(i.fps)} fps ({i.slowmo_factor:.3g}× slower).</span><br>"
            f"The app uses {fmt_rate(i.capture_fps)} fps as the original: speeds and "
            f"“× slower” refer to real time.")
