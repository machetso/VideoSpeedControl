# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Smart re-encode: copy everything, re-encode marked sections, join into one file."""
from __future__ import annotations

import subprocess
from fractions import Fraction

import pytest

from vsc.core import ffmpeg_bin, runner, segments as seg, smart
from vsc.core.job import Job, Mode, OutputSettings, Trim, output_path
from vsc.core.probe import FrameMap, probe, scan_frames


def _setup(clip, **kw):
    info, fm = probe(clip), scan_frames(clip)
    joins = smart.join_points(clip, info, fm)
    key = smart.SMART_CODECS[info.codec][0]
    s = OutputSettings(codec=key, smart=True, preset="ultrafast", **kw)
    job = Job(info, s, Trim(), FrameMap(fm.pts, fm.time_base, joins), [], joins)
    return job, fm


def _frame_hashes(path, first=None) -> list[str]:
    out = subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-i", str(path), "-map", "0:v:0",
                          "-fps_mode", "passthrough", "-f", "framemd5", "-"],
                         capture_output=True, text=True, check=True).stdout
    return [ln.rsplit(",", 1)[1].strip() for ln in out.splitlines() if not ln.startswith("#")]


def _packet_times(path) -> list[float]:
    out = subprocess.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams", "v",
                          "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.split()
    return sorted(float(x) for x in out)


def test_join_points(h264_clip, hevc10_clip, hevc_closed_clip):
    for clip in (h264_clip, hevc_closed_clip):
        info, fm = probe(clip), scan_frames(clip)
        assert smart.join_points(clip, info, fm) == fm.keyframes      # closed GOPs: all
    info, fm = probe(hevc10_clip), scan_frames(hevc10_clip)
    assert len(fm.keyframes) > 1
    assert smart.join_points(hevc10_clip, info, fm) == [0]           # open GOP: IDR only


def test_plan_widens_to_keyframes(h264_clip):
    job, fm = _setup(h264_clip)
    job.segments = [seg.Segment(30, 40, Fraction(25), reencode=True, out_fps=Fraction(25)),
                    seg.Segment(100, 120, Fraction(60))]                # copied section
    parts = smart.plan(job, job.joins)
    kinds = [(p.kind, p.start, p.end) for p in parts]
    assert kinds == [("copy", 0, 24), ("encode", 24, 48), ("copy", 48, fm.count)]
    assert job.mode == Mode.SMART and job.snaps_to_keyframes


@pytest.mark.parametrize("fixture", ["h264_clip", "hevc_closed_clip"])
@pytest.mark.parametrize("container", ["mp4", "mkv"])
def test_smart_export(request, tmp_path, fixture, container):
    clip = request.getfixturevalue(fixture)
    job, fm = _setup(clip, container=container)
    real = job.info.real_fps
    job.trim = Trim(0, 120)
    # 8× faster, re-encoded at 25 fps | copied original | copied slow-mo | re-encoded slow-mo
    job.segments = [seg.Segment(0, 40, real * 8, reencode=True, out_fps=Fraction(25)),
                    seg.Segment(60, 70, Fraction(25)),
                    seg.Segment(80, 90, Fraction(30), reencode=True, out_fps=Fraction(60))]
    parts = smart.plan(job, job.joins)
    assert [p.kind for p in parts] == ["encode", "copy", "encode", "copy"]
    out = output_path(job, tmp_path)
    run = runner.create(job, out)
    assert isinstance(run, smart.SmartRunner)
    res = run.run()
    assert res.ok, res.error

    dec = subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-i", str(out), "-fps_mode",
                          "passthrough", "-enc_time_base:v", "demux", "-f", "null", "-"],
                         capture_output=True, text=True)
    assert dec.returncode == 0 and not dec.stderr.strip(), dec.stderr[:500]
    hashes = _frame_hashes(out)
    assert len(hashes) == job.output_frame_count == sum(p.frames for p in parts)

    # copied frames are bit-identical to the source frames
    source = _frame_hashes(clip)
    pos = 0
    for p in parts:
        if p.kind == "copy":
            assert hashes[pos:pos + p.frames] == source[p.start:p.end]
        pos += p.frames

    # timing: total length and the copied slow-mo section's 40 ms frames
    ts = _packet_times(out)
    assert ts[-1] - ts[0] == pytest.approx(job.output_duration - float(
        1 / real), abs=0.012 if container == "mkv" else 0.002)
    copy2 = parts[1]
    first = sum(p.frames for p in parts[:1]) + (60 - copy2.start)
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    assert all(g == pytest.approx(0.04, abs=0.0015) for g in gaps[first:first + 9])

    if container == "mp4":
        tag = subprocess.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams", "v",
                              "-show_entries", "stream=codec_tag_string", "-of", "csv=p=0",
                              str(out)], capture_output=True, text=True).stdout.strip()
        assert tag == smart.SMART_CODECS[job.info.codec][1]


def test_open_gop_source_is_reencoded_whole(hevc10_clip, tmp_path):
    job, fm = _setup(hevc10_clip)
    job.trim = Trim(0, 60)
    job.segments = [seg.Segment(30, 40, Fraction(30), reencode=True, out_fps=Fraction(30))]
    parts = smart.plan(job, job.joins)
    assert [(p.kind, p.start, p.end) for p in parts] == [("encode", 0, 60)]
    res = runner.create(job, output_path(job, tmp_path)).run()
    assert res.ok, res.error


def test_not_available_for_other_codecs(hevc10_clip):
    info = probe(hevc10_clip)
    assert smart.unavailable_reason(info) is None
    info.codec = "prores"
    assert "H.264 or HEVC" in smart.unavailable_reason(info)


def test_rotation_is_kept(tmp_path):
    plain, rot = tmp_path / "plain.mp4", tmp_path / "rot.mp4"
    subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=320x180:r=240:d=0.5", "-c:v", "libx264", "-g", "24",
                    "-pix_fmt", "yuv420p", str(plain)], check=True)
    subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-display_rotation", "90", "-i",
                    str(plain), "-c", "copy", str(rot)], check=True)
    job, fm = _setup(rot)
    job.segments = [seg.Segment(30, 40, Fraction(25), reencode=True, out_fps=Fraction(25))]
    out = output_path(job, tmp_path / "out")
    res = runner.create(job, out).run()
    assert res.ok, res.error
    assert probe(out).rotation == probe(rot).rotation == 90
