# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Convert videos: folder search, names, jobs that keep everything, an AVI / DivX encode."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from vsc.core import batch, convert, ffmpeg_bin, runner
from vsc.core.job import Mode
from vsc.core.probe import probe, scan_frames

from conftest import _make


@pytest.fixture(scope="session")
def divx_clip() -> Path:
    """Like old DivX / Xvid files: AVI, MPEG-4 part 2, 10 fps, odd size, MP3 at 22.05 kHz."""
    return _make("divx_10fps.avi", [
        "-f", "lavfi", "-i", "testsrc2=s=368x208:r=10:d=3",
        "-f", "lavfi", "-i", "sine=f=440:d=3:sample_rate=22050", "-c:v", "mpeg4",
        "-vtag", "XVID", "-q:v", "4", "-c:a", "libmp3lame", "-ac", "2", "-b:a", "96k",
        "-shortest"])


def test_find_videos(tmp_path):
    (tmp_path / "sub" / ".hidden").mkdir(parents=True)
    for name in ("10 - b.AVI", "2 - a.mp4", "notes.txt", "sub/c.MKV", "sub/.hidden/d.mp4",
                 ".e.mp4"):
        (tmp_path / name).write_bytes(b"x")
    found = [p.relative_to(tmp_path).as_posix() for p in convert.find_videos([tmp_path])]
    assert found == ["2 - a.mp4", "10 - b.AVI", "sub/c.MKV"]       # natural order
    flat = convert.find_videos([tmp_path], recursive=False)
    assert [p.name for p in flat] == ["2 - a.mp4", "10 - b.AVI"]
    # a file chosen directly is kept whatever its extension; no duplicates
    both = convert.find_videos([tmp_path / "notes.txt", tmp_path / "2 - a.mp4", tmp_path],
                               recursive=False)
    assert [p.name for p in both] == ["notes.txt", "2 - a.mp4", "10 - b.AVI"]


def test_clean_stem():
    assert convert.clean_stem(Path("00 - Der Maulwurf Special.avi.MP4.MP4.AVI")) == \
        "00 - Der Maulwurf Special"
    assert convert.clean_stem(Path("09 - Der Fernseher..MP4.AVI")) == "09 - Der Fernseher"
    assert convert.clean_stem(Path("clip.final.mp4")) == "clip.final"
    assert convert.clean_stem(Path(".mp4.avi")) == "mp4"


def test_job_keeps_everything(divx_clip):
    info = probe(divx_clip)
    assert (info.codec, info.width, info.height, info.fps) == ("mpeg4", 368, 208, 10)
    job = convert.make_job(info, scan_frames(divx_clip), "x264", level=2)
    assert job.mode == Mode.REENCODE
    assert float(job.speed) == 1.0 and job.output_size() == (368, 208)
    assert job.container == "mp4" and job.settings.quality == 23
    assert job.output_frame_count == 30


def test_plan_names_and_folders(divx_clip, tmp_path):
    info = probe(divx_clip)
    job = convert.make_job(info, None, "x264")
    # default: "Converted" next to the original, extensions removed
    items = convert.plan([(job, None), (job, None)], None)
    assert items[0].output == divx_clip.parent / "Converted" / "divx_10fps.mp4"
    assert items[1].output.name == "divx_10fps_2.mp4"            # unique within the batch
    # chosen folder; an existing file is never overwritten
    (tmp_path / "divx_10fps.mp4").write_bytes(b"old")
    items = convert.plan([(job, None)], tmp_path)
    assert items[0].output == tmp_path / "divx_10fps_2.mp4"


def test_convert_divx_to_av1(divx_clip, tmp_path, encoder_status):
    if not encoder_status.get("svtav1") or not encoder_status["svtav1"].available:
        pytest.skip("SVT-AV1 not in this FFmpeg")
    info = probe(divx_clip)
    job = convert.make_job(info, scan_frames(divx_clip), "svtav1")
    items = convert.plan([(job, None)], tmp_path)
    result = batch.Batch(items).run()
    assert result.count("done") == 1, result.results
    out = probe(items[0].output)
    assert (out.codec, out.width, out.height, out.fps) == ("av1", 368, 208, 10)
    assert out.nb_frames == 30 or scan_frames(items[0].output).count == 30
    assert out.audio and out.audio.startswith("aac")
    assert abs(out.duration - 3.0) < 0.15
