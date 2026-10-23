"""Read clip information (ffprobe) and the frame/keyframe structure of a video stream."""
from __future__ import annotations

import json
import re
from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from . import ffmpeg_bin

TRANSFER_NAMES = {
    "bt709": "SDR (BT.709)",
    "smpte170m": "SDR (BT.601)",
    "bt470bg": "SDR (BT.601)",
    "iec61966-2-1": "SDR (sRGB)",
    "arib-std-b67": "HDR (HLG)",
    "smpte2084": "HDR (PQ / HDR10)",
}


def parse_rate(text: str | None) -> Fraction | None:
    if not text or text in ("0/0", "N/A"):
        return None
    try:
        r = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return r if r > 0 else None


def chroma_and_depth(pix_fmt: str) -> tuple[str, int]:
    """Derive chroma subsampling ('420'/'422'/'444') and bit depth from a pixel format name."""
    m = re.search(r"(\d+)(?:le|be)$", pix_fmt)
    if pix_fmt.startswith(("p010", "p210", "p410")):
        depth = 10
    elif m and not pix_fmt.startswith(("rgb24", "bgr24")):
        bits = int(m.group(1))
        # 'rgb48' / 'rgba64' describe the whole pixel, not one component
        depth = 16 if pix_fmt.startswith(("rgb48", "rgba64", "bgr48", "bgra64")) else bits
    else:
        depth = 8
    if pix_fmt.startswith(("yuv420", "yuvj420", "nv12", "nv21", "p010", "yuva420")):
        chroma = "420"
    elif pix_fmt.startswith(("yuv422", "yuvj422", "nv16", "p210", "yuyv422", "uyvy422", "yuva422", "y210")):
        chroma = "422"
    elif pix_fmt.startswith(("yuv411",)):
        chroma = "411"
    else:  # yuv444, rgb, gbr, gray ...
        chroma = "444"
    return chroma, depth


@dataclass
class MediaInfo:
    path: Path
    container: str
    container_long: str
    size_bytes: int
    duration: float
    bitrate: int | None
    codec: str
    codec_long: str
    profile: str | None
    width: int
    height: int
    sar: Fraction
    rotation: int
    pix_fmt: str
    chroma: str
    bit_depth: int
    fps: Fraction             # nominal frame rate (r_frame_rate)
    avg_fps: Fraction | None  # average over the file
    nb_frames: int | None
    start_time: float         # of the video stream
    format_start: float       # of the container; ffmpeg -ss is relative to this
    color_space: str | None
    color_transfer: str | None
    color_primaries: str | None
    color_range: str | None
    stream_bitrate: int | None
    has_audio: bool
    stream_index: int
    extra_streams: list[str] = field(default_factory=list)

    @property
    def display_size(self) -> tuple[int, int]:
        """Size as shown to the viewer (SAR and rotation applied)."""
        w = round(self.width * self.sar) if self.sar != 1 else self.width
        h = self.height
        return (h, w) if self.rotation % 180 else (w, h)

    @property
    def display_aspect(self) -> Fraction:
        w, h = self.display_size
        return Fraction(w, h)

    @property
    def is_hdr(self) -> bool:
        return self.color_transfer in ("arib-std-b67", "smpte2084")

    @property
    def transfer_label(self) -> str:
        return TRANSFER_NAMES.get(self.color_transfer or "", self.color_transfer or "unknown")

    @property
    def frame_count(self) -> int:
        if self.nb_frames:
            return self.nb_frames
        return round(self.duration * float(self.fps))

    @property
    def possibly_vfr(self) -> bool:
        if not self.avg_fps:
            return False
        return abs(float(self.avg_fps) / float(self.fps) - 1) > 0.01


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    res = ffmpeg_bin.run([
        ffmpeg_bin.ffprobe(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ], timeout=60)
    if res.returncode != 0:
        raise ValueError(f"Cannot read {path.name}: {res.stderr.strip() or 'unknown error'}")
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    videos = [s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")]
    if not videos:
        raise ValueError(f"{path.name} contains no video stream")
    v = videos[0]

    fps = parse_rate(v.get("r_frame_rate")) or parse_rate(v.get("avg_frame_rate"))
    if not fps:
        raise ValueError(f"{path.name}: frame rate unknown")

    rotation = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rotation = int(sd["rotation"]) % 360
    if not rotation and "rotate" in v.get("tags", {}):
        rotation = int(v["tags"]["rotate"]) % 360

    sar = parse_rate(v.get("sample_aspect_ratio", "1:1").replace(":", "/")) or Fraction(1)
    pix_fmt = v.get("pix_fmt", "unknown")
    chroma, depth = chroma_and_depth(pix_fmt)
    if v.get("bits_per_raw_sample", "").isdigit():
        depth = max(depth, int(v["bits_per_raw_sample"]))

    duration = float(v.get("duration") or fmt.get("duration") or 0)
    nb = v.get("nb_frames")
    extra = [f"{s.get('codec_type')}: {s.get('codec_name') or s.get('codec_tag_string')}"
             for s in streams if s is not v]

    return MediaInfo(
        path=path,
        container=fmt.get("format_name", "?"),
        container_long=fmt.get("format_long_name", ""),
        size_bytes=int(fmt.get("size") or path.stat().st_size),
        duration=duration,
        bitrate=int(fmt["bit_rate"]) if fmt.get("bit_rate", "").isdigit() else None,
        codec=v.get("codec_name", "?"),
        codec_long=v.get("codec_long_name", ""),
        profile=v.get("profile"),
        width=int(v["width"]),
        height=int(v["height"]),
        sar=sar,
        rotation=rotation,
        pix_fmt=pix_fmt,
        chroma=chroma,
        bit_depth=depth,
        fps=fps,
        avg_fps=parse_rate(v.get("avg_frame_rate")),
        nb_frames=int(nb) if nb and nb.isdigit() else None,
        start_time=float(v.get("start_time") or fmt.get("start_time") or 0),
        format_start=float(fmt.get("start_time") or 0),
        color_space=v.get("color_space"),
        color_transfer=v.get("color_transfer"),
        color_primaries=v.get("color_primaries"),
        color_range=v.get("color_range"),
        stream_bitrate=int(v["bit_rate"]) if v.get("bit_rate", "").isdigit() else None,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        stream_index=int(v["index"]),
        extra_streams=extra,
    )


@dataclass
class FrameMap:
    """Exact presentation timestamps of every frame plus keyframe indices.

    Built from packet headers only (no decoding), so it is fast even for long clips.
    """
    pts: list[int]          # sorted, in stream time base
    time_base: Fraction
    keyframes: list[int]    # frame indices (display order) of keyframes, ascending

    def __post_init__(self) -> None:
        tb = float(self.time_base)
        self.times = [p * tb for p in self.pts]   # seconds, for display and searching

    @property
    def count(self) -> int:
        return len(self.pts)

    def exact_time(self, frame: int) -> Fraction:
        return self.pts[frame] * self.time_base

    def frame_at(self, t: float) -> int:
        """Index of the frame shown at time t."""
        return max(0, bisect_right(self.times, t + 1e-9) - 1)

    def keyframe_at_or_before(self, frame: int) -> int:
        i = bisect_right(self.keyframes, frame) - 1
        return self.keyframes[max(i, 0)]

    def keyframe_after(self, frame: int) -> int:
        """First keyframe strictly after frame, or the frame count (end of clip)."""
        i = bisect_right(self.keyframes, frame)
        return self.keyframes[i] if i < len(self.keyframes) else self.count

    def snap_in(self, frame: int) -> int:
        """Nearest keyframe for an in-point."""
        before = self.keyframe_at_or_before(frame)
        after = self.keyframe_after(frame)
        if after < self.count and after - frame < frame - before:
            return after
        return before

    def snap_out(self, frame: int) -> int:
        """Nearest GOP boundary (exclusive end) for an out-point."""
        candidates = self.keyframes[1:] + [self.count]
        return min(candidates, key=lambda k: abs(k - frame))

    def frame_intervals(self) -> tuple[float, float]:
        """(min, max) distance between consecutive frames, for VFR detection."""
        d = [b - a for a, b in zip(self.times, self.times[1:])]
        return (min(d), max(d)) if d else (0.0, 0.0)


def scan_frames(path: str | Path, stream_index: int = 0) -> FrameMap:
    res = ffmpeg_bin.run([
        ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams", f"{stream_index}",
        "-show_entries", "stream=time_base:packet=pts,dts,flags", "-of", "csv=p=0", str(path),
    ], timeout=600)
    if res.returncode != 0:
        raise ValueError(f"Cannot scan frames: {res.stderr.strip()}")
    frames: list[tuple[int, bool]] = []
    time_base = Fraction(1, 1000)
    for line in res.stdout.splitlines():
        parts = line.split(",")
        if len(parts) == 1 and "/" in parts[0]:
            time_base = Fraction(parts[0])
            continue
        if len(parts) < 3:
            continue
        t = parts[0] if parts[0] not in ("", "N/A") else parts[1]
        if t in ("", "N/A"):
            continue
        frames.append((int(t), "K" in parts[2]))
    frames.sort()
    keys = [i for i, (_, k) in enumerate(frames) if k]
    if not keys and frames:
        keys = [0]
    return FrameMap(pts=[p for p, _ in frames], time_base=time_base, keyframes=keys)
