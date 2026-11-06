# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Turn a Job into an ffmpeg command line."""
from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

from . import ffmpeg_bin, segments as seg
from .encoders import hw_filter_suffix, hw_input_args
from .formats import COPY
from .job import Job, Mode
from ..i18n import tr

# Re-encode: seek slightly before the wanted frame; accurate seeking then starts exactly on it.
SEEK_EPS_FRAMES = 0.25

COLOR_ARGS = (("color_primaries", "-color_primaries"), ("color_transfer", "-color_trc"),
              ("color_space", "-colorspace"), ("color_range", "-color_range"))


def _num(v: Fraction | float) -> str:
    """Format a number for ffmpeg without float noise (up to 12 significant digits)."""
    return f"{float(v):.12g}"


class CommandError(ValueError):
    pass


def seek_time(job: Job, frame: int) -> float:
    frame_dur = 1 / float(job.info.fps)
    if job.frames and frame < job.frames.count:
        t = job.frames.times[frame] - job.info.format_start
    else:
        t = frame * frame_dur
    return max(0.0, t - SEEK_EPS_FRAMES * frame_dur)


def _copy_seek(job: Job, frame: int) -> str:
    """Seek target for stream copy: the keyframe's own time, rounded up to whole µs.

    ffmpeg seeks to the last keyframe at or before the target and subtracts the target from
    all timestamps. Hitting the keyframe time exactly keeps every timestamp on the frame grid;
    any offset would be scaled by -itsscale and cause 1-tick jitter.
    """
    if not job.frames:
        raise CommandError("Frame map required for trimming")
    t = job.frames.exact_time(frame) - Fraction(job.info.format_start).limit_denominator(10**6)
    return f"{max(0, math.ceil(t * 1_000_000))}us"


def _base_args() -> list[str]:
    return [ffmpeg_bin.ffmpeg(), "-hide_banner", "-y", "-v", "error",
            "-progress", "pipe:1", "-nostats"]


def _stream_args(job: Job) -> list[str]:
    return ["-map", f"0:{job.info.stream_index}", "-an", "-sn", "-dn",
            "-map_metadata", "0", "-map_chapters", "-1"]


def build(job: Job, output: Path, supported_pix_fmts: list[str] | None = None) -> list[str]:
    if job.source_frame_count <= 0:
        raise CommandError(tr("Trim range is empty"))
    if job.mode == Mode.RETIME:
        return _build_copy(job, output)
    return _build_encode(job, output, supported_pix_fmts)


def _build_copy(job: Job, output: Path) -> list[str]:
    blockers = job.retime_blockers()
    if blockers:
        raise CommandError(tr("Lossless retime not possible: %s", "; ".join(blockers)))
    return copy_args(job, output, "setts" if job.has_segments else "itsscale")


def copy_args(job: Job, output: Path, timing: str) -> list[str]:
    """Stream copy of the trim range; timing 'setts' (per frame, sections) or 'itsscale'."""
    args = _base_args()
    if job.trim.start:
        args += ["-ss", _copy_seek(job, job.trim.start)]
    if timing == "setts":
        args += ["-i", str(job.info.path)] + _stream_args(job) + ["-c:v", "copy"]
        args += ["-bsf:v", _setts(job)]
    else:
        # -itsscale stretches every timestamp: 240 fps played at 25 fps -> factor 9.6.
        # ffmpeg truncates scaled timestamps, so a tiny upward bias avoids losing one tick.
        scale = float(job.info.fps / Fraction(job.settings.fps)) * (1 + 1e-11)
        args += ["-itsscale", f"{scale:.17g}", "-i", str(job.info.path)]
        args += _stream_args(job) + ["-c:v", "copy"]
    if job.trim.start or job.trim.end is not None:
        # frames are counted in decode order; a GOP is complete, so this ends on its boundary
        args += ["-frames:v", str(job.source_frame_count)]
    if job.info.codec == "hevc" and job.container in ("mp4", "mov"):
        args += ["-tag:v", "hvc1"]
    args += ["-avoid_negative_ts", "make_zero", str(output)]
    return args


def _setts(job: Job) -> str:
    """Speed sections without re-encoding: rewrite every packet's timestamps (VFR output)."""
    fm = job.frames
    if not fm:
        raise CommandError("Frame map required for speed sections")
    ps = job.pieces()
    # the last frame's own length in the file (for the end of the last piece)
    last = fm.pts[-1] - fm.pts[-2] if fm.count > 1 else 1
    end_pts = fm.pts[-1] + last

    def f(var):
        return seg.setts_expr(ps, fm.pts, fm.time_base, var, end_pts)
    return (f"setts=pts='{f('PTS')}':dts='{f('DTS')}'"
            f":duration='{f('(PTS+DURATION)')}-({f('PTS')})'")


def scale_filters(job: Job) -> list[str]:
    s = job.settings
    if s.resize == "source":
        return []
    w, h = job.output_size()
    flags = f"flags={s.scaler}"
    if s.resize == "fit_box" or s.fit == "stretch":
        return [f"scale={w}:{h}:{flags}", "setsar=1"]
    src_w, src_h = job.info.display_size
    if s.fit == "pad":
        f = min(w / src_w, h / src_h)
    else:  # crop
        f = max(w / src_w, h / src_h)
    iw = max(2, round(src_w * f / 2) * 2)
    ih = max(2, round(src_h * f / 2) * 2)
    chain = [f"scale={iw}:{ih}:{flags}", "setsar=1"]
    if s.fit == "pad":
        chain.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
    else:
        chain.append(f"crop={w}:{h}")
    return chain


def _time_filters(job: Job) -> list[str]:
    out_fps = Fraction(job.settings.fps)
    # Re-time by frame number so that slightly irregular source timestamps cannot cause jitter
    if job.has_segments:
        if job.settings.interpolation not in ("dup", "blend", "mci"):
            raise CommandError(tr("RIFE cannot be combined with speed sections – "
                                  "choose another interpolation"))
        chain = [f"setpts='({seg.setpts_expr(job.pieces())})/TB'"]   # quoted: commas inside
    else:
        rate = job.info.real_fps * job.speed  # source frames per output second
        chain = [f"setpts=N/({_num(rate)})/TB"]
    mode = job.mode
    if mode in (Mode.REENCODE, Mode.DROP):
        chain.append(f"fps={out_fps}")
        return chain
    method = job.settings.interpolation
    if method == "dup":
        chain.append(f"fps={out_fps}")
    elif method == "blend":
        chain.append(f"framerate=fps={out_fps}")
    elif method == "mci":
        # minterpolate stops at the last source timestamp; two cloned frames let it reach the end
        chain.insert(0, "tpad=stop_mode=clone:stop=2")
        chain.append(f"minterpolate=fps={out_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
    else:
        raise CommandError(f"Interpolation '{method}' is not implemented yet")
    return chain


def pixel_filters(job: Job, pix_fmt: str) -> list[str]:
    """Last filters: convert to the encoder's pixel format (or upload to the GPU)."""
    if job.codec.hw:
        return hw_filter_suffix(job.codec, pix_fmt)
    return [f"format={pix_fmt}"]


def encode_args(job: Job, output: Path) -> list[str]:
    """Everything after the filters: encoder, its options, colour tags and the output."""
    codec, s = job.codec, job.settings
    args = ["-c:v", codec.encoder]
    if profile := job.profile:
        args += list(profile.args)
    if codec.preset_flag and codec.presets:
        preset = s.preset if s.preset in codec.presets else codec.default_preset
        args += [codec.preset_flag, preset]
    by_rate = bool(s.bitrate) and codec.quality is not None and not codec.lossless
    if by_rate:                     # fixed data rate instead of constant quality
        args += ["-b:v", f"{int(s.bitrate)}k"]
    elif codec.quality:
        q = s.quality if s.quality is not None else codec.quality.default
        q = min(max(q, codec.quality.minimum), codec.quality.maximum)
        args += [a.replace("{q}", str(q)) for a in codec.quality.args]
    args += _without_zero_rate(codec.args) if by_rate else list(codec.args)
    args += list(codec.container_args.get(job.container, ()))
    if not codec.rgb:
        for attr, flag in COLOR_ARGS:
            value = getattr(job.info, attr)
            if value and value != "unknown":
                args += [flag, value]
    if codec.image_sequence:
        args += ["-f", "image2"]
    args.append(str(output))
    return args


def _without_zero_rate(args) -> list[str]:
    """Codec args minus '-b:v 0' (libaom / libvpx need it for constant quality only)."""
    out, it = [], iter(args)
    for a in it:
        if a == "-b:v":
            nxt = next(it, None)
            if nxt == "0":
                continue
            out += [a, nxt]
        else:
            out.append(a)
    return out


def _build_encode(job: Job, output: Path, supported: list[str] | None) -> list[str]:
    codec = job.codec
    if codec is None:
        raise CommandError(f"Unknown codec '{job.settings.codec}'")
    if codec.external:
        raise CommandError(f"{codec.label} runs outside FFmpeg (see runner.create)")
    chroma, depth, pix_fmt = job.output_format(supported)
    return decode_args(job, pix_fmt) + encode_args(job, output)


def decode_args(job: Job, pix_fmt: str) -> list[str]:
    """ffmpeg input, trimming, retiming and scaling up to the encoder (without it)."""
    codec = job.codec
    filters: list[str] = []
    if job.trim.end is not None:
        filters.append(f"trim=end_frame={job.source_frame_count}")
    scale = scale_filters(job)
    time = _time_filters(job)
    if job.mode == Mode.DROP or not shrinks(job):
        filters += time + scale     # scale fewer frames / interpolate on fewer pixels
    else:
        filters += scale + time
    filters += pixel_filters(job, pix_fmt)

    args = _base_args() + hw_input_args(codec)
    if job.trim.start:
        args += ["-ss", _num(seek_time(job, job.trim.start))]
    args += ["-i", str(job.info.path)] + _stream_args(job)
    args += ["-vf", ",".join(filters), "-frames:v", str(job.output_frame_count)]
    return args


def shrinks(job: Job) -> bool:
    w, h = job.output_size()
    src_w, src_h = job.info.display_size
    return w * h < src_w * src_h
