# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Speed sections: piece arithmetic, lossless VFR export and constant-rate re-encode."""
from __future__ import annotations

import subprocess
from dataclasses import replace
from fractions import Fraction

import pytest

from vsc.core import ffmpeg_bin, playback, segments as seg
from vsc.core.formats import COPY
from vsc.core.job import Job, Mode, OutputSettings, Trim, output_path
from vsc.core.probe import probe, scan_frames
from vsc.core.runner import Runner


def test_add_overlapping_sections():
    s = seg.add([], seg.Segment(10, 50, Fraction(25)))
    s = seg.add(s, seg.Segment(30, 40, Fraction(60)))
    assert s == [seg.Segment(10, 30, Fraction(25)), seg.Segment(30, 40, Fraction(60)),
                 seg.Segment(40, 50, Fraction(25))]
    assert seg.add(s, seg.Segment(0, 100, Fraction(30))) == [seg.Segment(0, 100, Fraction(30))]


def test_pieces_and_times():
    ps = seg.pieces([seg.Segment(100, 150, Fraction(25))], 0, 300, Fraction(240))
    assert [(p.start, p.end, p.rate) for p in ps] == [(0, 100, 240), (100, 150, 25), (150, 300, 240)]
    assert seg.duration(ps) == Fraction(100, 240) + Fraction(50, 25) + Fraction(150, 240)
    assert seg.output_time(ps, 100) == Fraction(100, 240)
    assert seg.source_frame(ps, float(Fraction(100, 240)) + 0.041) == 101
    # trimmed into the section
    ps = seg.pieces([seg.Segment(100, 150, Fraction(25))], 120, 140, Fraction(240))
    assert [(p.start, p.end, p.rate) for p in ps] == [(120, 140, 25)]


def _frame_times(path) -> list[float]:
    out = subprocess.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams", "v",
                          "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.split()
    return sorted(float(x) for x in out)


def _job(clip, **kw):
    info = probe(clip)
    fm = scan_frames(clip)
    job = Job(info, OutputSettings(**kw), frames=fm)
    return job


@pytest.mark.parametrize("trimmed", [False, True])
def test_lossless_sections_vfr(h264_clip, tmp_path, trimmed):
    job = _job(h264_clip, codec=COPY)
    fm = job.frames
    if trimmed:
        job.trim = Trim(fm.keyframes[1], fm.keyframes[3])
    a = job.trim.start + 7                      # sections start at any frame
    job.segments = [seg.Segment(a, a + 10, Fraction(25))]
    assert job.mode == Mode.RETIME and not job.retime_blockers()
    out = output_path(job, tmp_path)
    res = Runner(job, out).run()
    assert res.ok, res.error
    ts = _frame_times(out)
    assert len(ts) == job.source_frame_count
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    real = 1 / float(job.info.real_fps)
    rel = a - job.trim.start
    assert gaps[rel - 1] == pytest.approx(real, abs=2e-4)            # before the section
    assert all(g == pytest.approx(0.04, abs=2e-4) for g in gaps[rel:rel + 10])
    assert gaps[rel + 10] == pytest.approx(real, abs=2e-4)           # after it
    assert ts[-1] - ts[0] + real == pytest.approx(job.output_duration, abs=2e-3)


def test_sections_reencoded_cfr(h264_clip, tmp_path):
    job = _job(h264_clip, codec="x264", fps=Fraction(50))
    job.trim = Trim(0, 120)
    job.segments = [seg.Segment(40, 60, Fraction(25))]
    assert job.mode == Mode.INTERPOLATE           # 25 fps section in a 50 fps output
    out = output_path(job, tmp_path)
    res = Runner(job, out).run()
    assert res.ok, res.error
    ts = _frame_times(out)
    assert abs(len(ts) - job.output_frame_count) <= 1
    gaps = {round(b - a, 4) for a, b in zip(ts, ts[1:])}
    assert gaps == {0.02}                          # constant 50 fps


def test_playback_plan_with_sections(h264_clip):
    job = _job(h264_clip, codec=COPY)
    job.segments = [seg.Segment(10, 20, Fraction(25))]
    plan = playback.plan(job, 0, (160, 90))
    assert plan.fps == playback.PREVIEW_VFR_FPS
    assert plan.source_frame(0) == 0
    t = float(seg.output_time(job.pieces(), 15))
    assert plan.source_frame(round(t * float(plan.fps))) in (14, 15)


def test_speedup_section_lossless_and_cfr(h264_clip, tmp_path):
    job = _job(h264_clip, codec=COPY)
    job.trim = Trim(0, 120)
    fast = job.info.real_fps * 8                     # 8× faster than real time
    job.segments = [seg.Segment(0, 80, fast)]
    assert job.output_duration == pytest.approx(80 / float(fast) + 40 / float(job.info.real_fps))
    out = output_path(job, tmp_path)
    res = Runner(job, out).run()
    assert res.ok, res.error
    ts = _frame_times(out)
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    assert len(ts) == 120
    assert all(g == pytest.approx(1 / float(fast), abs=2e-5) for g in gaps[:79])
    assert gaps[80] == pytest.approx(1 / float(job.info.real_fps), abs=2e-5)

    job.settings.container = "mkv"
    assert any("Matroska" in r for r in job.retime_blockers())

    cfr = _job(h264_clip, codec="x264", fps=Fraction(60))
    cfr.trim, cfr.segments = Trim(0, 120), list(job.segments)
    assert cfr.mode == Mode.DROP
    out = output_path(cfr, tmp_path / "cfr")
    res = Runner(cfr, out).run()
    assert res.ok, res.error
    ts = _frame_times(out)
    assert abs(len(ts) - cfr.output_frame_count) <= 1
    assert {round(b - a, 4) for a, b in zip(ts, ts[1:])} == {round(1 / 60, 4)}


# ---------------------------------------------------------------------- speed ramps (v0.92)

RAMP_WANT = """
    292 293 107/4|293 295 121/4|295 296 135/4|296 298 149/4|298 300 163/4|300 303 177/4|303 305 191/4|
    305 307 205/4|307 310 219/4|310 313 233/4|374 377 69|377 382 87|382 387 105|387 393 123|393 400 141|
    400 408 159|408 417 177|417 427 195|427 437 213|437 449 231|477 483 459/2|483 488 417/2|488 492 375/2|
    492 496 333/2|496 500 291/2|500 503 249/2|503 505 207/2|505 508 165/2|508 509 123/2|509 510 81/2
"""


def test_ramp_steps_like_android():
    """The same frames as the Android app's RampTest (exact fractions, half-even rounding)."""
    segs = [seg.Segment(100, 300, Fraction(25), smooth_end=True),
            seg.Segment(300, 400, Fraction(60), smooth_end=True),
            seg.Segment(500, 520, Fraction(30), smooth_start=True)]
    got = [f"{s.start} {s.end} {s.fps}" for s in seg.ramp_steps(segs, 0, 600, Fraction(240))]
    assert got == "".join(RAMP_WANT.split("\n")).replace("    ", "").split("|")


def test_cut_drops_the_smooth_flag():
    s = seg.Segment(100, 300, Fraction(25), smooth_start=True, smooth_end=True)
    assert seg.add([s], seg.Segment(150, 200, Fraction(60))) == [
        seg.Segment(100, 150, Fraction(25), smooth_start=True),
        seg.Segment(150, 200, Fraction(60)),
        seg.Segment(200, 300, Fraction(25), smooth_end=True)]


def test_smart_ramps_follow_the_reencoded_neighbour(h264_clip):
    job = _job(h264_clip, codec="x264")
    job.settings.smart = True
    job.segments = [seg.Segment(100, 300, Fraction(25), smooth_end=True),
                    seg.Segment(300, 600, Fraction(60), True, Fraction(30), smooth_start=True)]
    steps = [s for s in job.timing_segments if s.fps not in (Fraction(25), Fraction(60))]
    assert steps and all(s.reencode and s.out_fps == Fraction(30) for s in steps)
    job.segments = [replace(s, reencode=False, out_fps=None) for s in job.segments]
    assert not any(s.reencode for s in job.timing_segments)        # both copied: the ramp too


def test_lossless_ramp_vfr(h264_clip, tmp_path):
    """Frame durations grow step by step from real time to the section's rate."""
    job = _job(h264_clip, codec=COPY)
    job.segments = [seg.Segment(300, 500, Fraction(30), smooth_start=True)]
    out = output_path(job, tmp_path)
    res = Runner(job, out).run()
    assert res.ok, res.error
    ts = _frame_times(out)
    assert len(ts) == job.source_frame_count
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    ramp = gaps[240:340]                     # the ramp: frames 253–321
    assert all(b >= a - 2e-4 for a, b in zip(ramp, ramp[1:]))     # slowing down evenly
    assert ramp[0] == pytest.approx(1 / float(job.info.real_fps), abs=2e-4)
    assert ramp[-1] == pytest.approx(1 / 30, abs=2e-4)
    real = 1 / float(job.info.real_fps)
    assert ts[-1] - ts[0] + real == pytest.approx(job.output_duration, abs=3e-3)


def test_editing_rules_like_android():
    F = Fraction
    assert seg.quick_start([], 300) == 0
    a = [seg.Segment(0, 300, F(25))]
    assert seg.quick_start(a, 500) == 300                    # right after the section before
    b = a + [seg.Segment(300, 500, F(60))]
    assert seg.quick_start(b, 400) == 300                    # inside a section: split it
    assert seg.quick_start([], 100, trim_start=10) == 10
    assert seg.borders(b, 960) == [300, 500]
    assert seg.border_range(b, 300, 960) == (1, 499)
    assert seg.moved_border(b, 300, 350, 960) == [seg.Segment(0, 350, F(25)), seg.Segment(350, 500, F(60))]
    assert seg.moved_border(b, 300, 900, 960)[0].end == 499
    assert seg.border_range(b, 500, 960) == (301, 960)
    s = seg.with_smooth(b, 300, True)
    assert s[0].smooth_end and s[1].smooth_start
    assert seg.neighbour_rate(s, 1, True, 960, F(240)) == F(25)
    assert seg.neighbour_rate(s, 1, False, 960, F(240)) == F(240)
    assert seg.neighbour_rate(s, 0, True, 960, F(240)) is None
