# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Real-time preview of the output: decode at reduced size, retime like the export, raw RGB out.

Nothing is encoded: ffmpeg decodes the source, scales it down first (cheap) and applies the
same retiming as the export. Interpolation that cannot run in real time (minterpolate, RIFE)
is shown as blending – the timing is right, the in-between pictures are not.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from . import ffmpeg_bin, segments as seg
from .command import _num, seek_time
from .formats import COPY
from .job import Job
from ..i18n import tr

PREVIEW_MAX = (960, 540)
PREVIEW_VFR_FPS = Fraction(60)   # variable-rate output is previewed like a 60 Hz screen shows it
FAST_DECODE_RATE = 100     # source frames per second above which decoding cuts corners
SLOW_INTERPOLATIONS = ("mci",)    # plus every RIFE variant (see is_slow)


@dataclass
class PlayPlan:
    args: list[str]
    size: tuple[int, int]
    fps: Fraction             # output frames per second
    start: int                # first source frame
    frame_ratio: float        # output frames per source frame
    note: str = ""            # e.g. "interpolation shown as blending"
    pieces: list | None = None   # speed sections: timing per run of frames

    def source_frame(self, n: int) -> int:
        """Source frame shown by output frame n."""
        if self.pieces:
            return seg.source_frame(self.pieces, n / float(self.fps))
        return self.start + int(n / self.frame_ratio)


def is_slow(method: str) -> bool:
    return method in SLOW_INTERPOLATIONS or method.startswith("rife")


def plan(job: Job, start: int, size: tuple[int, int]) -> PlayPlan:
    """Play from source frame `start` to the end of the trim range at output speed."""
    end = job.trim.end if job.trim.end is not None else job.total_frames
    start = max(job.trim.start, min(start, end - 1))
    w, h = size
    out_fps = Fraction(job.settings.fps)
    rate = job.info.real_fps * job.speed      # source frames per output second
    ratio = job.frame_ratio
    note = ""
    chain = [f"trim=end_frame={end - start}",
             f"scale={w}:{h}:flags=fast_bilinear", "setsar=1"]
    pieces = None
    if job.has_segments or job.settings.smart:
        pieces = job.pieces(start)
        rate = max(p.rate for p in pieces)
        if job.settings.codec == COPY or job.settings.smart:
            out_fps = PREVIEW_VFR_FPS
            note = tr("Variable frame rate, previewed at %d fps.", PREVIEW_VFR_FPS)
        chain.append(f"setpts='({seg.setpts_expr(pieces)})/TB'")
        ratio = float(out_fps / min(p.rate for p in pieces))   # > 1 if any part is stretched
    else:
        chain.append(f"setpts=N/({_num(rate)})/TB")
    method = job.settings.interpolation
    variable = pieces and (job.settings.codec == COPY or job.settings.smart)
    if ratio > 1 + 1e-6 and method != "dup" and not variable:
        chain.append(f"framerate=fps={out_fps}")
        if is_slow(method):
            note = tr("Preview shows the interpolation as blending (the real one is too slow).")
    else:
        chain.append(f"fps={out_fps}")
    args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-nostdin"]
    if rate > FAST_DECODE_RATE:
        # ~15 % faster decoding (measured on HEVC 1080p); slightly blockier, fine for a preview
        args += ["-flags2", "fast", "-skip_loop_filter", "all"]
    if start:
        args += ["-ss", _num(seek_time(job, start))]
    args += ["-i", str(job.info.path), "-map", f"0:{job.info.stream_index}", "-an", "-sn", "-dn",
             "-vf", ",".join(chain), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return PlayPlan(args, (w, h), out_fps, start, ratio, note, pieces)
