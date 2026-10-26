# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Per-clip output settings and the decision which processing mode applies."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from pathlib import Path

from . import formats, segments as seg
from .formats import COPY, CODECS_BY_KEY
from .probe import FrameMap, MediaInfo


class Mode(Enum):
    RETIME = "retime"            # A: stream copy, only timestamps change
    REENCODE = "reencode"        # every source frame used once, but re-encoded (resize, codec ...)
    DROP = "drop"                # B: frame selection
    INTERPOLATE = "interpolate"  # C: new in-between frames
    SMART = "smart"              # copy, re-encode only marked sections, join (smart.py)


MODE_LABELS = {
    Mode.RETIME: "Lossless retime (no re-encoding)",
    Mode.REENCODE: "Re-encode, every frame used once",
    Mode.DROP: "Frame selection (frames are skipped)",
    Mode.INTERPOLATE: "Interpolation (in-between frames are calculated)",
    Mode.SMART: "Smart re-encode (only marked sections are re-encoded)",
}

KEYFRAME_TRIM_REASON = (
    "Without re-encoding, cuts are only possible at keyframes: only keyframes are complete "
    "pictures. All other frames merely store the differences to their neighbours and cannot "
    "be decoded once the preceding keyframe is cut away."
)

SPEED_EPS = 1e-6
MKV_MAX_FPS = 500      # 1 ms timestamps: faster frames would collide / jitter


@dataclass
class OutputSettings:
    """Everything the user chooses for one clip. Copied to other clips by 'apply to all'."""
    fps: Fraction = formats.DEFAULT_FPS
    speed: Fraction | None = None          # None = lossless speed (out fps / source fps)
    codec: str = COPY
    container: str | None = None           # None = codec default
    profile: str | None = None
    preset: str | None = None
    quality: int | None = None
    chroma: str | None = None              # None = like source (if possible)
    depth: int | None = None               # None = like source (if possible)
    resize: str = "source"                 # 'source' | 'fit_box' | 'exact'
    width: int | None = None
    height: int | None = None
    fit: str = "pad"                       # for 'exact': 'pad' | 'crop' | 'stretch'
    scaler: str = formats.DEFAULT_SCALER
    interpolation: str = formats.DEFAULT_INTERPOLATION
    smart: bool = False                    # smart re-encode (codec = the source's encoder)
    audio: bool = True                     # keep the sound (stretched, pitch preserved)

    def clone(self) -> "OutputSettings":
        return copy.deepcopy(self)


@dataclass
class Trim:
    """Source range in frames: [start, end). end=None means until the end of the clip."""
    start: int = 0
    end: int | None = None


@dataclass
class Job:
    info: MediaInfo
    settings: OutputSettings = field(default_factory=OutputSettings)
    trim: Trim = field(default_factory=Trim)
    frames: FrameMap | None = None   # needed for keyframe snapping and exact cuts
    segments: list[seg.Segment] = field(default_factory=list)   # speed sections (per clip)
    joins: list[int] | None = None   # smart re-encode: safe keyframes (None = not analysed)

    # ------------------------------------------------------------------ speed sections

    @property
    def trim_end(self) -> int:
        total = self.total_frames
        return min(self.trim.end, total) if self.trim.end is not None else total

    @property
    def has_segments(self) -> bool:
        """Sections inside the trim range: they replace the global speed."""
        return any(s.start < self.trim_end and s.end > self.trim.start for s in self.segments)

    def pieces(self, start: int | None = None) -> list[seg.Piece]:
        """The trim range (from `start`) as runs of one rate; outside sections: real time."""
        first = self.trim.start if start is None else start
        return seg.pieces(self.segments, first, self.trim_end, self.info.real_fps)

    def output_time(self, frame: int) -> float:
        """Time in the output at which source frame `frame` appears."""
        if self.has_segments:
            return float(seg.output_time(self.pieces(), frame))
        return (frame - self.trim.start) / float(self.info.real_fps * self.speed)

    # ------------------------------------------------------------------ speed

    @property
    def lossless_speed(self) -> Fraction:
        return Fraction(self.settings.fps) / self.info.real_fps

    @property
    def speed(self) -> Fraction:
        if self.settings.smart or self.has_segments:   # average speed over the whole output
            real = Fraction(self.source_frame_count) / self.info.real_fps
            out = Fraction(self.output_duration).limit_denominator(10**9) or Fraction(1)
            return (real / out).limit_denominator(100000)
        return self.settings.speed if self.settings.speed is not None else self.lossless_speed

    @property
    def frame_ratio(self) -> float:
        """Output frames per source frame (1 = every frame used once)."""
        if self.settings.smart or self.has_segments:
            return self.output_frame_count / max(1, self.source_frame_count)
        return float(Fraction(self.settings.fps) / (self.speed * self.info.real_fps))

    @property
    def is_lossless_speed(self) -> bool:
        if self.settings.smart:
            return True        # untouched parts are copied; sections bring their own timing
        if self.has_segments:
            return self.settings.codec == COPY
        return abs(self.frame_ratio - 1) < SPEED_EPS

    # ------------------------------------------------------------------ mode

    @property
    def codec(self) -> formats.Codec | None:
        return CODECS_BY_KEY.get(self.settings.codec)

    @property
    def mode(self) -> Mode:
        if self.settings.smart:
            return Mode.SMART
        if self.settings.codec == COPY:
            return Mode.RETIME
        if self.has_segments:
            out = Fraction(self.settings.fps)
            rates = {p.rate for p in self.pieces()}
            if any(r < out for r in rates):
                return Mode.INTERPOLATE
            return Mode.DROP if any(r > out for r in rates) else Mode.REENCODE
        r = self.frame_ratio
        if abs(r - 1) < SPEED_EPS:
            return Mode.REENCODE
        return Mode.INTERPOLATE if r > 1 else Mode.DROP

    def retime_blockers(self) -> list[str]:
        """Why lossless retime (stream copy) is impossible with the current settings."""
        s = self.settings
        reasons = []
        if not self.has_segments and not self.is_lossless_speed:
            reasons.append(
                f"Speed {float(self.speed):.4g}× differs from the lossless speed "
                f"{float(self.lossless_speed):.4g}× at {float(s.fps):.5g} fps")
        if s.resize != "source":
            reasons.append("Resizing requires re-encoding")
        if self.frames and not self.trim_on_keyframes():
            reasons.append("Trim points are not on keyframes")
        if (self.has_segments and self.container == "mkv"
                and max(p.rate for p in self.pieces()) > MKV_MAX_FPS):
            reasons.append("Matroska stores timestamps in milliseconds – too coarse for sections "
                           f"above {MKV_MAX_FPS} fps; choose MP4 or MOV")
        return reasons

    def trim_on_keyframes(self) -> bool:
        fm = self.frames
        start, end = self.trim.start, self.trim.end
        if start and start not in fm.keyframes:
            return False
        return end is None or end >= fm.count or end in fm.keyframes

    # ------------------------------------------------------------------ trimming

    @property
    def total_frames(self) -> int:
        return self.frames.count if self.frames else self.info.frame_count

    @property
    def snaps_to_keyframes(self) -> bool:
        """Mode A can only cut at keyframes (see KEYFRAME_TRIM_REASON)."""
        return self.mode in (Mode.RETIME, Mode.SMART) and self.frames is not None

    def trim_with_in(self, frame: int) -> Trim:
        """Trim with a new in-point (first frame); the out-point is dropped if it is before."""
        frame = max(0, min(frame, self.total_frames - 1))
        if self.snaps_to_keyframes:
            frame = self.frames.snap_in(frame)
        end = self.trim.end
        return Trim(frame, None if end is not None and end <= frame else end)

    def trim_with_out(self, last: int) -> Trim:
        """Trim with a new out-point; `last` is the last frame to include."""
        total = self.total_frames
        end = max(1, min(last + 1, total))
        if self.snaps_to_keyframes:
            end = self.frames.snap_out(end)
        start = self.trim.start if end > self.trim.start else 0
        return Trim(start, None if end >= total else end)

    def snapped_trim(self) -> Trim:
        """The current trim moved to the nearest keyframes / GOP boundaries."""
        fm = self.frames
        start = fm.snap_in(self.trim.start)
        end = fm.snap_out(self.trim.end) if self.trim.end is not None else None
        if end is not None and end <= start:
            end = fm.keyframe_after(start)
        return Trim(start, None if end is None or end >= fm.count else end)

    # ------------------------------------------------------------------ frame counts

    @property
    def source_frame_count(self) -> int:
        total = self.frames.count if self.frames else self.info.frame_count
        end = min(self.trim.end, total) if self.trim.end is not None else total
        return max(0, end - self.trim.start)

    def smart_parts(self) -> list:
        from . import smart
        return smart.plan(self, self.joins or [])

    @property
    def output_frame_count(self) -> int:
        if self.settings.smart:
            return max(1, sum(p.frames for p in self.smart_parts()))
        if self.has_segments:
            if self.settings.codec == COPY:      # every frame kept, each with its own duration
                return self.source_frame_count
            return max(1, round(seg.duration(self.pieces()) * Fraction(self.settings.fps)))
        return max(1, round(self.source_frame_count * self.frame_ratio))

    @property
    def output_duration(self) -> float:
        if self.settings.smart:
            return float(sum(p.duration for p in self.smart_parts()))
        if self.has_segments:
            return float(seg.duration(self.pieces()))
        return self.output_frame_count / float(self.settings.fps)

    # ------------------------------------------------------------------ output format

    @property
    def container(self) -> str:
        s = self.settings
        if s.smart:
            return s.container if s.container in ("mp4", "mkv") else "mp4"
        if s.codec == COPY:
            allowed = formats.copy_containers(self.info.codec)
            if s.container in allowed:
                return s.container
            src_ext = self.info.path.suffix.lower().lstrip(".")
            return src_ext if src_ext in allowed else "mkv"
        c = self.codec
        return s.container if s.container in c.containers else c.containers[0]

    @property
    def profile(self) -> formats.Profile | None:
        c = self.codec
        if not c or not c.profiles:
            return None
        key = self.settings.profile or c.default_profile
        return next((p for p in c.profiles if p.key == key), c.profiles[0])

    def output_format(self, supported: list[str] | None = None) -> tuple[str, int, str]:
        """(chroma, depth, pix_fmt) – the requested one if possible, else the closest."""
        c = self.codec
        allowed = formats.allowed_formats(c, self.profile, supported)
        if not allowed:
            raise ValueError(f"{c.label}: no usable pixel format")
        want_chroma = self.settings.chroma or self.info.chroma
        want_depth = self.settings.depth or min(10, max(8, self.info.bit_depth))
        if (want_chroma, want_depth) in allowed:
            chroma, depth = want_chroma, want_depth
        else:
            def distance(cd):
                return (cd[0] != want_chroma) * 2 + (cd[1] != want_depth)
            chroma, depth = min(allowed, key=distance)
        return chroma, depth, formats.pixel_format(c, chroma, depth, supported)

    def output_size(self) -> tuple[int, int]:
        """Size of the encoded frame (even numbers)."""
        s = self.settings
        src_w, src_h = self.info.display_size
        if s.resize == "source" or not (s.width or s.height):
            w, h = src_w, src_h
        elif s.resize == "fit_box":
            box_w, box_h = s.width or 10**6, s.height or 10**6
            scale = min(box_w / src_w, box_h / src_h)
            w, h = src_w * scale, src_h * scale
        else:
            w = s.width or round(s.height * src_w / src_h)
            h = s.height or round(s.width * src_h / src_w)
        return _even(w), _even(h)

    def default_output_name(self) -> str:
        if self.settings.smart:
            return f"{self.info.path.stem}_smart"
        if self.has_segments:
            rate = ("vfr" if self.settings.codec == COPY
                    else f"{float(self.settings.fps):.5g}fps".replace(".", "_"))
            return f"{self.info.path.stem}_sections_{rate}"
        sp = f"{float(self.speed):.3g}".replace(".", "_")
        fps = f"{float(self.settings.fps):.5g}".replace(".", "_")
        return f"{self.info.path.stem}_{sp}x_{fps}fps"


def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def output_path(job: Job, folder: Path, name: str | None = None) -> Path:
    name = name or job.default_output_name()
    ext = formats.CONTAINER_EXT[job.container]
    if job.codec and job.codec.image_sequence:
        return folder / name / f"{name}_%06d{ext}"
    return folder / f"{name}{ext}"
