# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Command line front end of the core – for testing and scripting.

    python -m vsc info  CLIP...
    python -m vsc encode CLIP -o OUT_DIR [--fps 25] [--speed 0.1] [--codec x264] ...
    python -m vsc encoders
"""
from __future__ import annotations

import argparse
import sys
from fractions import Fraction
from pathlib import Path

from .core import encoders, formats
from .core.job import KEYFRAME_TRIM_REASON, MODE_LABELS, Job, Mode, OutputSettings, Trim, output_path
from .core.probe import probe, scan_frames
from .core import runner as runners


def _fmt_rate(r: Fraction) -> str:
    return f"{float(r):.6g}"


def cmd_info(args) -> None:
    for p in args.clips:
        i = probe(p)
        fm = scan_frames(p, i.stream_index)
        gop = (fm.keyframes[1] - fm.keyframes[0]) if len(fm.keyframes) > 1 else fm.count
        lo, hi = fm.frame_intervals()
        print(f"{i.path.name}")
        print(f"  Container : {i.container_long} ({i.size_bytes / 1e6:.1f} MB)")
        print(f"  Codec     : {i.codec} {i.profile or ''} – {i.codec_long}")
        print(f"  Size      : {i.width}×{i.height}  SAR {i.sar}  rotation {i.rotation}°"
              f"  → display {i.display_size[0]}×{i.display_size[1]}")
        print(f"  Frame rate: {_fmt_rate(i.fps)} fps (avg {_fmt_rate(i.avg_fps or i.fps)})"
              f"  {'VFR?' if i.possibly_vfr or hi > lo * 1.5 else 'constant'}")
        print(f"  Frames    : {fm.count}  duration {i.duration:.3f}s  keyframes {len(fm.keyframes)}"
              f" (GOP ≈ {gop})")
        print(f"  Pixel fmt : {i.pix_fmt}  chroma {i.chroma[0]}:{i.chroma[1]}:{i.chroma[2]}"
              f"  {i.bit_depth}-bit  {i.transfer_label}")
        print(f"  Bitrate   : {(i.stream_bitrate or i.bitrate or 0) / 1e6:.1f} Mbit/s")
        print(f"  Other     : {', '.join(i.extra_streams) or '–'}")
        print(f"  Device    : {i.device or '–'}")
        print(f"  Recorded  : {i.recorded:%Y-%m-%d %H:%M:%S}" if i.recorded else "  Recorded  : –")
        print(f"  Audio     : {i.audio or '–'} (not exported)")
        if i.slowmo_factor:
            print(f"  Slow-mo   : recorded at {_fmt_rate(i.capture_fps)} fps – the file is already "
                  f"{i.slowmo_factor:.3g}× slow motion")
        for fps_label, fps in formats.FRAME_RATES:
            print(f"    lossless @ {fps_label:9}: {float(fps / i.real_fps):.5f}×"
                  f"  ({float(i.real_fps / fps):.3g}× slower)")


def cmd_encoders(args) -> None:
    for key, st in encoders.detect(use_cache=not args.refresh).items():
        c = formats.CODECS_BY_KEY[key]
        print(f"{'✓' if st.available else '✗'} {c.label:42} {st.reason}")


def cmd_encode(args) -> None:
    info = probe(args.clip)
    frames = scan_frames(args.clip, info.stream_index)
    s = OutputSettings(
        fps=Fraction(args.fps), codec=args.codec,
        speed=Fraction(args.speed) if args.speed else None,
        container=args.container, profile=args.profile, preset=args.preset,
        quality=args.quality, chroma=args.chroma, depth=args.depth,
        interpolation=args.interp, scaler=args.scaler,
    )
    if args.size:
        w, h = (int(v) for v in args.size.lower().split("x"))
        s.resize, s.width, s.height, s.fit = args.resize, w, h, args.fit
    trim = Trim(args.start or 0, args.end)
    if s.codec == formats.COPY:
        trim = Trim(frames.snap_in(trim.start),
                    frames.snap_out(trim.end) if trim.end is not None else None)
        if (trim.start, trim.end) != (args.start or 0, args.end):
            print(f"Trim snapped to keyframes: {trim.start}–{trim.end}. {KEYFRAME_TRIM_REASON}")
    job = Job(info, s, trim, frames)

    print(f"Mode  : {MODE_LABELS[job.mode]}")
    print(f"Speed : {float(job.speed):.5g}×  ({job.source_frame_count} → "
          f"{job.output_frame_count} frames, {job.output_duration:.2f}s)")
    if job.mode == Mode.RETIME and (b := job.retime_blockers()):
        sys.exit("Lossless retime not possible:\n  " + "\n  ".join(b))
    supported = None
    if job.codec:
        st = encoders.detect()[job.codec.key]
        if not st.available:
            sys.exit(f"{job.codec.label} not available: {st.reason}")
        supported = st.pix_fmts
        chroma, depth, pix = job.output_format(supported)
        print(f"Format: {job.output_size()[0]}×{job.output_size()[1]} {pix}")

    out = output_path(job, Path(args.output), args.name)
    runner = runners.create(job, out, supported)
    if args.show_cmd:
        print(" ".join(runner.args))

    def progress(p):
        eta = f"{p.eta:5.0f}s" if p.eta is not None else "  ?"
        print(f"\r  {p.fraction:6.1%}  {p.frame}/{p.total_frames}  {p.fps:6.1f} fps  ETA {eta}",
              end="", flush=True)

    res = runner.run(progress)
    print()
    if not res.ok:
        sys.exit(f"Failed:\n{res.error}")
    print(f"Done: {res.output}  ({res.elapsed:.1f}s, {res.fps:.1f} fps)")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="vsc", description="VideoSpeedControl core")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="show clip information")
    p.add_argument("clips", nargs="+")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("encoders", help="list available encoders")
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(func=cmd_encoders)

    p = sub.add_parser("encode", help="convert one clip")
    p.add_argument("clip")
    p.add_argument("-o", "--output", default=".")
    p.add_argument("--name")
    p.add_argument("--fps", default="25")
    p.add_argument("--speed", help="e.g. 0.25 or 1/8; default = lossless speed")
    p.add_argument("--codec", default=formats.COPY, choices=[formats.COPY, *formats.CODECS_BY_KEY])
    p.add_argument("--container")
    p.add_argument("--profile")
    p.add_argument("--preset")
    p.add_argument("--quality", type=int)
    p.add_argument("--chroma", choices=["420", "422", "444"])
    p.add_argument("--depth", type=int, choices=[8, 10])
    p.add_argument("--size", help="WxH")
    p.add_argument("--resize", default="exact", choices=["fit_box", "exact"])
    p.add_argument("--fit", default="pad", choices=list(formats.FIT_MODES))
    p.add_argument("--scaler", default=formats.DEFAULT_SCALER, choices=[s.key for s in formats.SCALERS])
    p.add_argument("--interp", default=formats.DEFAULT_INTERPOLATION,
                   choices=[i.key for i in formats.INTERPOLATIONS])
    p.add_argument("--start", type=int, help="first source frame")
    p.add_argument("--end", type=int, help="end source frame (exclusive)")
    p.add_argument("--show-cmd", action="store_true")
    p.set_defaults(func=cmd_encode)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
