"""Single frames as images – for the preview and the timeline thumbnails."""
from __future__ import annotations

import subprocess

from . import ffmpeg_bin
from .probe import FrameMap, MediaInfo

# Seek slightly before the wanted frame; accurate seeking then delivers exactly that frame.
SEEK_EPS_FRAMES = 0.25


def fit_size(info: MediaInfo, max_w: int, max_h: int) -> tuple[int, int]:
    """Display size scaled down (never up) to fit max_w × max_h, even numbers."""
    w, h = info.display_size
    f = min(1.0, max_w / w, max_h / h)
    return max(2, round(w * f / 2) * 2), max(2, round(h * f / 2) * 2)


def frame_args(info: MediaInfo, frames: FrameMap, index: int, size: tuple[int, int],
               accurate: bool = True) -> list[str]:
    """ffmpeg arguments that write frame `index` as one BMP image to stdout.

    accurate=False is much faster but returns the keyframe at or before `index`.
    """
    index = max(0, min(index, frames.count - 1))
    t = frames.times[index] - info.format_start - SEEK_EPS_FRAMES / float(info.fps)
    w, h = size
    args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-nostdin"]
    if not accurate:
        args += ["-noaccurate_seek", "-skip_frame", "nokey"]
    args += ["-ss", f"{max(0.0, t):.6f}", "-i", str(info.path),
             "-map", f"0:{info.stream_index}", "-an", "-sn", "-dn", "-frames:v", "1",
             "-vf", f"scale={w}:{h}:flags=bilinear,setsar=1",
             "-c:v", "bmp", "-pix_fmt", "bgr24", "-f", "image2pipe", "-"]
    return args


def grab_frame(info: MediaInfo, frames: FrameMap, index: int, size: tuple[int, int],
               accurate: bool = True, timeout: float = 60) -> bytes:
    """Frame `index` as BMP data (display orientation, square pixels, `size`)."""
    res = subprocess.run(frame_args(info, frames, index, size, accurate), capture_output=True,
                         timeout=timeout, **ffmpeg_bin.POPEN_FLAGS)
    if res.returncode != 0 or not res.stdout:
        msg = res.stderr.decode("utf-8", "replace").strip() or "no image"
        raise ValueError(f"Cannot read frame {index}: {msg}")
    return res.stdout


def thumbnail_frames(frames: FrameMap, count: int) -> list[int]:
    """`count` evenly spread keyframes (thumbnails use fast keyframe seeking)."""
    if frames.count == 0:
        return []
    picks = []
    for i in range(count):
        target = round((i + 0.5) * frames.count / count)
        k = frames.keyframe_at_or_before(min(target, frames.count - 1))
        picks.append(k)
    return picks
