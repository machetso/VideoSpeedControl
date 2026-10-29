# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Clip speed treatment files (.cst): speed sections, trim and output settings of one clip.

A treatment belongs to exactly one video: it stores a fingerprint of the file (size + SHA-256
of three 1 MiB pieces) and only loads onto a file with the same fingerprint and frame count.
The file name does not matter, so a renamed or moved clip still matches.
JSON, fractions as strings ("240000/1001").
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from fractions import Fraction
from pathlib import Path

from . import segments as seg
from .formats import CODECS_BY_KEY, COPY
from .job import OutputSettings, Trim

SUFFIX = ".cst"
FORMAT = "VideoSpeedControl clip speed treatment"
VERSION = 1
_CHUNK = 1 << 20
_FRACTIONS = {"fps", "speed"}            # OutputSettings fields stored as fractions


class TreatmentError(Exception):
    """The file cannot be read, or it belongs to another video."""


def fingerprint(path: Path) -> str:
    """Identity of the video file's content: size + first, middle and last MiB."""
    size = path.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with path.open("rb") as f:
        for offset in sorted({0, max(0, size // 2 - _CHUNK // 2), max(0, size - _CHUNK)}):
            f.seek(offset)
            h.update(f.read(_CHUNK))
    return h.hexdigest()


@dataclass
class Treatment:
    source_name: str                  # file name when saved (shown in messages only)
    source_size: int
    fingerprint: str
    frames: int                       # frame count of the source
    settings: OutputSettings
    ui: dict = field(default_factory=dict)
    trim: Trim = field(default_factory=Trim)
    segments: list[seg.Segment] = field(default_factory=list)
    source_path: str = ""             # where the clip was when saved (to find it again)

    def check(self, path: Path, frames: int) -> None:
        """Raise TreatmentError unless `path` is the video this treatment was made for."""
        if path.stat().st_size != self.source_size or fingerprint(path) != self.fingerprint:
            raise TreatmentError(
                f"This treatment belongs to another video: {self.source_name} "
                f"({self.source_size:,} bytes, {self.frames} frames).\n"
                f"{path.name} is a different file, so its sections and trim would not fit.")
        if frames != self.frames:
            raise TreatmentError(f"{path.name} has {frames} frames, the treatment was made for "
                                 f"{self.frames} frames.")


def save(target: Path, source: Path, frames: int, settings: OutputSettings, ui: dict,
         trim: Trim, segments: list[seg.Segment]) -> None:
    data = {
        "format": FORMAT,
        "version": VERSION,
        "source": {"name": source.name, "path": str(source), "size": source.stat().st_size,
                   "fingerprint": fingerprint(source), "frames": frames},
        "settings": {f.name: _out(getattr(settings, f.name)) for f in fields(OutputSettings)},
        "ui": ui,
        "trim": {"start": trim.start, "end": trim.end},
        "sections": [{"start": s.start, "end": s.end, "fps": str(s.fps),
                      "reencode": s.reencode,
                      "out_fps": str(s.out_fps) if s.out_fps is not None else None,
                      "smooth_start": s.smooth_start, "smooth_end": s.smooth_end}
                     for s in segments],
    }
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path) -> Treatment:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != FORMAT:
            raise TreatmentError(f"{path.name} is not a clip speed treatment file.")
        if data.get("version", 0) > VERSION:
            raise TreatmentError(f"{path.name} was saved by a newer version of "
                                 "VideoSpeedControl.")
        src = data["source"]
        known = {f.name for f in fields(OutputSettings)}
        settings = OutputSettings(**{k: _in(k, v) for k, v in data["settings"].items()
                                     if k in known})
        if settings.codec != COPY and settings.codec not in CODECS_BY_KEY:
            raise TreatmentError(f"Unknown codec “{settings.codec}” in {path.name}.")
        trim = Trim(int(data["trim"]["start"]),
                    None if data["trim"]["end"] is None else int(data["trim"]["end"]))
        sections = [seg.Segment(int(s["start"]), int(s["end"]), Fraction(s["fps"]),
                                bool(s.get("reencode", False)),
                                Fraction(s["out_fps"]) if s.get("out_fps") else None,
                                bool(s.get("smooth_start", False)), bool(s.get("smooth_end", False)))
                    for s in data["sections"]]
        return Treatment(src["name"], int(src["size"]), src["fingerprint"], int(src["frames"]),
                         settings, dict(data.get("ui") or {}), trim, sections,
                         src.get("path", ""))
    except TreatmentError:
        raise
    except (OSError, UnicodeDecodeError) as e:
        raise TreatmentError(f"{path.name} cannot be read: {e}") from e
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
        raise TreatmentError(f"{path.name} is damaged or incomplete ({e}).") from e


def _out(value):
    return str(value) if isinstance(value, Fraction) else value


def _in(key: str, value):
    return Fraction(value) if key in _FRACTIONS and value is not None else value
