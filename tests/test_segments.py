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
