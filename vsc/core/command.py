"""Turn a Job into an ffmpeg command line."""
from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

from . import ffmpeg_bin
from .encoders import hw_filter_suffix, hw_input_args
from .formats import COPY
from .job import Job, Mode

# Re-encode: seek slightly before the wanted frame; accurate seeking then starts exactly on it.
SEEK_EPS_FRAMES = 0.25

COLOR_ARGS = (("color_primaries", "-color_primaries"), ("color_transfer", "-color_trc"),
              ("color_space", "-colorspace"), ("color_range", "-color_range"))


def _num(v: Fraction | float) -> str:
    """Format a number for ffmpeg without float noise (up to 12 significant digits)."""
    return f"{float(v):.12g}"


class CommandError(ValueError):
    pass


def _seek_time(job: Job, frame: int) -> float:
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
        raise CommandError("Trim range is empty")
    if job.mode == Mode.RETIME:
        return _build_copy(job, output)
    return _build_encode(job, output, supported_pix_fmts)


def _build_copy(job: Job, output: Path) -> list[str]:
    blockers = job.retime_blockers()
    if blockers:
        raise CommandError("Lossless retime not possible: " + "; ".join(blockers))
    args = _base_args()
    if job.trim.start:
        args += ["-ss", _copy_seek(job, job.trim.start)]
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


def _scale_filters(job: Job) -> list[str]:
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
    rate = job.info.fps * job.speed  # source frames per output second
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


def _build_encode(job: Job, output: Path, supported: list[str] | None) -> list[str]:
    codec = job.codec
    if codec is None:
        raise CommandError(f"Unknown codec '{job.settings.codec}'")
    chroma, depth, pix_fmt = job.output_format(supported)
    s = job.settings

    filters: list[str] = []
    if job.trim.end is not None:
        filters.append(f"trim=end_frame={job.source_frame_count}")
    scale = _scale_filters(job)
    time = _time_filters(job)
    w, h = job.output_size()
    src_w, src_h = job.info.display_size
    shrinking = w * h < src_w * src_h
    if job.mode == Mode.DROP or not shrinking:
        filters += time + scale     # scale fewer frames / interpolate on fewer pixels
    else:
        filters += scale + time
    if codec.hw:
        filters += hw_filter_suffix(codec, pix_fmt)
    else:
        filters.append(f"format={pix_fmt}")

    args = _base_args() + hw_input_args(codec)
    if job.trim.start:
        args += ["-ss", _num(_seek_time(job, job.trim.start))]
    args += ["-i", str(job.info.path)] + _stream_args(job)
    args += ["-vf", ",".join(filters), "-frames:v", str(job.output_frame_count)]

    args += ["-c:v", codec.encoder]
    if profile := job.profile:
        args += list(profile.args)
    if codec.preset_flag and codec.presets:
        preset = s.preset if s.preset in codec.presets else codec.default_preset
        args += [codec.preset_flag, preset]
    if codec.quality:
        q = s.quality if s.quality is not None else codec.quality.default
        q = min(max(q, codec.quality.minimum), codec.quality.maximum)
        args += [a.replace("{q}", str(q)) for a in codec.quality.args]
    args += list(codec.args)
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
