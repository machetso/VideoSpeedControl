# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""The list of imported clips: one Clip per file, shown in a QTableView."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSettings, Qt
from PySide6.QtGui import QColor

from ..core import formats, segments as seg, testencode
from ..core.job import Job, Mode, OutputSettings, Trim
from ..core.probe import FrameMap, MediaInfo


class Status(Enum):
    PROBING = "Reading…"
    SCANNING = "Scanning frames…"
    READY = "Ready"
    ERROR = "Error"


MODE_SHORT = {
    Mode.SMART: "Smart re-encode",
    Mode.RETIME: "A – lossless retime",
    Mode.REENCODE: "Re-encode",
    Mode.DROP: "B – frame selection",
    Mode.INTERPOLATE: "C – interpolation",
}


HISTORY = 200        # undo steps kept per clip


@dataclass
class Clip:
    path: Path
    status: Status = Status.PROBING
    info: MediaInfo | None = None
    frames: FrameMap | None = None
    error: str = ""
    settings: OutputSettings = field(default_factory=OutputSettings)
    # Widget choices that OutputSettings cannot express (e.g. which resolution preset or
    # aspect ratio was picked). Copied together with the settings by "apply to all".
    ui: dict = field(default_factory=dict)
    trim: Trim = field(default_factory=Trim)          # per clip, never copied to other clips
    segments: list = field(default_factory=list)      # speed sections, per clip like the trim
    thumbs: list = field(default_factory=list)        # [(frame index, QImage)], filled in background
    playhead: int = 0
    test: testencode.TestResult | None = None     # last test encode
    test_media: object = None                       # workers.TestMedia of its output
    testing: bool = False
    export: str = ""                                  # export state for the Status column
    removed: bool = False                             # tells background tasks to stop

    proxy: list = field(default_factory=list)         # small JPEG per (step-th) frame
    proxy_step: int = 1
    proxy_done: bool = False
    joins: list | None = None                         # smart re-encode: safe keyframes
    fingerprint: str | None = None                    # content identity (stored preview, .cst)
    _smart_frames: FrameMap | None = None
    # section edits: [(description, sections before the edit)], newest last
    undo_steps: list = field(default_factory=list)
    redo_steps: list = field(default_factory=list)

    def edit_segments(self, segments: list, what: str) -> bool:
        """Replace the speed sections; the old list can be brought back with undo()."""
        if list(segments) == self.segments:
            return False
        self.undo_steps.append((what, list(self.segments)))
        del self.undo_steps[:-HISTORY]
        self.redo_steps.clear()
        self.segments[:] = segments
        return True

    def undo(self) -> str | None:
        """Step back one section edit; returns its description (None = nothing to undo)."""
        return self._step(self.undo_steps, self.redo_steps)

    def redo(self) -> str | None:
        return self._step(self.redo_steps, self.undo_steps)

    def _step(self, source: list, target: list) -> str | None:
        if not source:
            return None
        what, segments = source.pop()
        target.append((what, list(self.segments)))
        self.segments[:] = segments
        return what

    @property
    def job(self) -> Job | None:
        if not self.info:
            return None
        frames = self.frames
        if self.settings.smart and self.joins is not None and frames:
            # smart re-encode can only cut / join at safe keyframes: snap to those
            if self._smart_frames is None or self._smart_frames.pts is not frames.pts:
                self._smart_frames = FrameMap(frames.pts, frames.time_base, self.joins)
            frames = self._smart_frames
        # Easy mode smooths every speed change (no switches); Pro uses the sections' own flags
        segments = seg.all_smooth(self.segments) if easy_mode() else self.segments
        return Job(self.info, self.settings, self.trim, frames, segments, self.joins)


def easy_mode() -> bool:
    """Easy / Pro switch of the output settings (Easy is the default)."""
    value = QSettings().value("settings/pro", False)
    return value not in (True, "true", "1", 1)


def fmt_rate(r) -> str:
    return f"{float(r):.6g}"


def fmt_duration(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:06.3f}" if h else f"{m}:{s:06.3f}"


def frame_rate_choices(real_fps) -> list[tuple[str, "Fraction"]]:
    """The standard rates plus the clip's own rate, marked as original, sorted by rate."""
    rates = []
    for label, fps in formats.FRAME_RATES:
        name, _, extra = label.partition(" ")
        rates.append((f"{name} fps {extra}".strip(), fps))
    for i, (label, fps) in enumerate(rates):
        if fps == real_fps:
            rates[i] = (f"{label} (original)", fps)
            return rates
    rates.append((f"{fmt_rate(real_fps)} fps (original)", real_fps))
    return sorted(rates, key=lambda r: r[1])


def fmt_slowdown(factor: float) -> str:
    """How much slower (factor > 1) or faster than the original, e.g. '8× slower'."""
    if abs(factor - 1) < 1e-4:
        return "real time"
    if factor > 1:
        return f"{factor:.3g}× slower"
    return f"{1 / factor:.3g}× faster"


def fmt_seconds(seconds: float) -> str:
    if seconds == float("inf"):
        return "?"
    if seconds < 10:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        m, s = divmod(round(seconds), 60)
        return f"{m}:{s:02d} min" if m else f"{s} s"
    h, rest = divmod(round(seconds), 3600)
    return f"{h}:{rest // 60:02d} h"


def fmt_bytes(n: int) -> str:
    for unit, size in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= size:
            return f"{n / size:.3g} {unit}"
    return f"{n} B"


def chroma_label(chroma: str) -> str:
    return ":".join(chroma) if len(chroma) == 3 else chroma


class ClipModel(QAbstractTableModel):
    COLUMNS = ("File", "Device", "Codec", "Resolution", "FPS", "Frames", "Duration", "Format",
               "Output", "Estimate", "Status")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clips: list[Clip] = []

    # ------------------------------------------------------------------ Qt API

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.clips)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        clip = self.clips[index.row()]
        col = self.COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            if col == "Estimate":
                return self._estimate_text(clip)
            return self._text(clip, col)
        if role == Qt.ToolTipRole:
            if col == "File":
                return str(clip.path)
            if clip.status == Status.ERROR:
                return clip.error
            if col == "FPS" and clip.info and clip.info.slowmo_factor:
                i = clip.info
                return (f"Recorded at {fmt_rate(i.capture_fps)} fps, stored at {fmt_rate(i.fps)} fps:\n"
                        f"the file is already {i.slowmo_factor:.3g}× slow motion.\n"
                        f"{fmt_rate(i.capture_fps)} fps is used as the original frame rate.")
            if col == "Device" and clip.info and clip.info.recorded:
                return f"Recorded {clip.info.recorded:%Y-%m-%d %H:%M}"
            if col == "Estimate":
                return ("Time and size for the whole (trimmed) clip.\n"
                        "Measured by a test encode of this clip, or ≈ scaled from a test of\n"
                        "another clip with identical settings. Run a test encode for a value.")
        if role == Qt.ForegroundRole:
            if clip.status == Status.ERROR:
                return QColor("#c0392b")
            if col == "FPS" and clip.info and (clip.info.possibly_vfr or clip.info.slowmo_factor):
                return QColor("#d35400")
        return None

    @staticmethod
    def _text(clip: Clip, col: str) -> str:
        if col == "File":
            return clip.path.name
        if col == "Status":
            return clip.export or clip.status.value
        i = clip.info
        if i is None:
            return ""
        if col == "Device":
            return (i.device or "").split(" (firmware")[0]
        if col == "Codec":
            return f"{i.codec} {i.profile}" if i.profile else i.codec
        if col == "Resolution":
            w, h = i.display_size
            return f"{w}×{h}"
        if col == "FPS":
            text = fmt_rate(i.real_fps) + (" (VFR?)" if i.possibly_vfr else "")
            if i.slowmo_factor:
                text += f" (slow-mo, file {fmt_rate(i.fps)})"
            return text
        if col == "Frames":
            job = clip.job
            if clip.trim.start or clip.trim.end is not None:
                return f"{job.source_frame_count} of {job.total_frames}"
            return str(job.total_frames)
        if col == "Duration":
            return fmt_duration(i.duration)
        if col == "Format":
            return f"{chroma_label(i.chroma)} {i.bit_depth}-bit"
        if col == "Output":
            job = clip.job
            if job.mode == Mode.SMART:
                return "Smart re-encode"
            if job.has_segments:
                return ("Sections – lossless (VFR)" if job.mode == Mode.RETIME else
                        f"Sections → {fmt_rate(job.settings.fps)} fps")
            return MODE_SHORT[job.mode]
        return ""

    # ------------------------------------------------------------------ estimates

    def estimate(self, clip: Clip) -> testencode.Estimate | None:
        if not clip.info:
            return None
        others = [c.test for c in self.clips if c is not clip and c.test]
        return testencode.estimate(clip.job, clip.test, others)

    def _estimate_text(self, clip: Clip) -> str:
        if clip.testing:
            return "testing…"
        est = self.estimate(clip)
        if est is None:
            return ""
        return f"{'' if est.exact else '≈ '}{fmt_seconds(est.seconds)}, {fmt_bytes(est.bytes)}"

    def batch_estimate(self) -> tuple[float, int, int]:
        """(seconds, bytes, clips without estimate) for all usable clips."""
        seconds, size, missing = 0.0, 0, 0
        for clip in self.clips:
            if clip.status == Status.ERROR:
                continue
            est = self.estimate(clip)
            if est is None:
                missing += 1
            else:
                seconds, size = seconds + est.seconds, size + est.bytes
        return seconds, size, missing

    def refresh_all(self) -> None:
        if self.clips:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self.clips) - 1, len(self.COLUMNS) - 1))

    # ------------------------------------------------------------------ editing

    def add(self, path: Path) -> Clip | None:
        """Append a clip; returns None if the file is already in the list."""
        if any(c.path == path for c in self.clips):
            return None
        row = len(self.clips)
        self.beginInsertRows(QModelIndex(), row, row)
        clip = Clip(path)
        self.clips.append(clip)
        self.endInsertRows()
        return clip

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            clip = self.clips[row]
            clip.removed = True
            testencode.discard(clip.test)
            del self.clips[row]
            self.endRemoveRows()

    def clip_changed(self, clip: Clip) -> None:
        if clip in self.clips:
            row = self.clips.index(clip)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.COLUMNS) - 1))
