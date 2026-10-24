"""The list of imported clips: one Clip per file, shown in a QTableView."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from ..core import testencode
from ..core.job import Job, Mode, OutputSettings, Trim
from ..core.probe import FrameMap, MediaInfo


class Status(Enum):
    PROBING = "Reading…"
    SCANNING = "Scanning frames…"
    READY = "Ready"
    ERROR = "Error"


MODE_SHORT = {
    Mode.RETIME: "A – lossless retime",
    Mode.REENCODE: "Re-encode",
    Mode.DROP: "B – frame selection",
    Mode.INTERPOLATE: "C – interpolation",
}


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
    thumbs: list = field(default_factory=list)        # [(frame index, QImage)], filled in background
    playhead: int = 0
    test: testencode.TestResult | None = None     # last test encode
    test_media: object = None                       # workers.TestMedia of its output
    testing: bool = False
    removed: bool = False                             # tells background tasks to stop

    @property
    def job(self) -> Job | None:
        return Job(self.info, self.settings, self.trim, self.frames) if self.info else None


def fmt_rate(r) -> str:
    return f"{float(r):.6g}"


def fmt_duration(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:06.3f}" if h else f"{m}:{s:06.3f}"


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
    COLUMNS = ("File", "Codec", "Resolution", "FPS", "Frames", "Duration", "Format",
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
            if col == "Estimate":
                return ("Time and size for the whole (trimmed) clip.\n"
                        "Measured by a test encode of this clip, or ≈ scaled from a test of\n"
                        "another clip with identical settings. Run a test encode for a value.")
        if role == Qt.ForegroundRole:
            if clip.status == Status.ERROR:
                return QColor("#c0392b")
            if col == "FPS" and clip.info and clip.info.possibly_vfr:
                return QColor("#d35400")
        return None

    @staticmethod
    def _text(clip: Clip, col: str) -> str:
        if col == "File":
            return clip.path.name
        if col == "Status":
            return clip.status.value
        i = clip.info
        if i is None:
            return ""
        if col == "Codec":
            return f"{i.codec} {i.profile}" if i.profile else i.codec
        if col == "Resolution":
            w, h = i.display_size
            return f"{w}×{h}"
        if col == "FPS":
            return fmt_rate(i.fps) + (" (VFR?)" if i.possibly_vfr else "")
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
            return MODE_SHORT[clip.job.mode]
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
