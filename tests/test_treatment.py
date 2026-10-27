# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Clip speed treatment files (.cst) and the name additions of the batch list."""
from __future__ import annotations

import shutil
from fractions import Fraction

import pytest

from vsc.core import batch, probe, segments as seg, treatment
from vsc.core.job import Job, OutputSettings, Trim


def test_round_trip_and_binding(tmp_path, h264_clip, hevc10_clip):
    settings = OutputSettings(fps=Fraction(30000, 1001), speed=Fraction(1, 8), codec="x265",
                              preset="slow", quality=20, resize="exact", width=1280, height=720)
    sections = [seg.Segment(10, 50, Fraction(25)),
                seg.Segment(60, 90, Fraction(60), reencode=True, out_fps=Fraction(30))]
    cst = tmp_path / "clip.cst"
    treatment.save(cst, h264_clip, 958, settings, {"res": "720p", "aspect": "fit"},
                   Trim(5, 200), sections)
    t = treatment.load(cst)
    assert t.settings == settings and t.segments == sections
    assert (t.trim.start, t.trim.end) == (5, 200) and t.ui["res"] == "720p"
    assert t.source_name == "h264_240.mp4" and t.frames == 958

    t.check(h264_clip, 958)
    renamed = tmp_path / "renamed.mp4"              # name does not matter, content does
    shutil.copy(h264_clip, renamed)
    t.check(renamed, 958)
    with pytest.raises(treatment.TreatmentError, match="another video"):
        t.check(hevc10_clip, 958)
    with pytest.raises(treatment.TreatmentError, match="frames"):
        t.check(h264_clip, 957)
    with renamed.open("r+b") as f:                  # same size, changed content
        f.seek(100)
        f.write(b"\0" * 16)
    with pytest.raises(treatment.TreatmentError, match="another video"):
        t.check(renamed, 958)


def test_load_rejects_bad_files(tmp_path):
    bad = tmp_path / "bad.cst"
    bad.write_text("{not json")
    with pytest.raises(treatment.TreatmentError, match="damaged"):
        treatment.load(bad)
    bad.write_text('{"format": "something else"}')
    with pytest.raises(treatment.TreatmentError, match="not a clip speed treatment"):
        treatment.load(bad)
    with pytest.raises(treatment.TreatmentError, match="cannot be read"):
        treatment.load(tmp_path / "missing.cst")


def test_name_additions(h264_clip, tmp_path):
    info = probe.probe(h264_clip)
    copy_job = Job(info, OutputSettings())
    assert batch.addition_parts(copy_job) == {"codec": "copy", "preset": None, "quality": None,
                                              "res": None}
    job = Job(info, OutputSettings(codec="x265", preset="slow", width=640, height=360,
                                   resize="exact"))
    assert batch.addition(job, ("codec", "preset", "quality", "res")) == "_x265_slow_high_640x360"
    job.settings.quality = 25
    assert batch.addition(job, ("quality",)) == "_good"
    job.settings.quality = 21
    assert batch.addition(job, ("quality",)) == "_crf21"
    assert batch.addition(job, ()) == ""
    items = batch.plan([(copy_job, None), (job, None)], tmp_path, "{name}", batch.RENAME,
                       [(), ("codec", "res")])
    assert [it.output.stem for it in items] == ["h264_240", "h264_240_x265_640x360"]
