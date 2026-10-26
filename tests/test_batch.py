# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Batch export: names, overwrite policy, running, cancelling."""
from __future__ import annotations

import shutil
import threading
from fractions import Fraction
from pathlib import Path

import pytest

from vsc.core import batch
from vsc.core.job import Job, OutputSettings, Trim
from vsc.core.probe import probe, scan_frames


def _job(clip: Path, **kw) -> Job:
    info = probe(clip)
    trim = kw.pop("trim", Trim())
    return Job(info, OutputSettings(**kw), trim, scan_frames(clip, info.stream_index))


@pytest.fixture
def src(tmp_path, h264_clip) -> Path:
    """The test clip copied into an empty folder, so outputs can go next to it."""
    folder = tmp_path / "src"
    folder.mkdir()
    return Path(shutil.copy(h264_clip, folder / "clip.mp4"))


def test_render_name(src):
    job = _job(src, fps=Fraction(25), codec="x264", resize="exact", width=640, height=360)
    assert batch.render_name(batch.DEFAULT_PATTERN, job) == job.default_output_name()
    assert batch.render_name("{n}-{name}-{codec}-{res}-{slower}x", job, 3) == \
        "03-clip-x264-640x360-9_59x"
    assert batch.render_name("a/b:{unknown}", job) == "a_b_{unknown}"
    assert batch.render_name(" .. ", job) == "clip"


def test_plan_policies(src, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    job = _job(src)                                        # copy → .mp4
    first = batch.plan([(job, None)], out, "x", batch.RENAME)[0]
    assert first.output == out / "x.mp4" and first.note == ""

    (out / "x.mp4").write_bytes(b"old")
    renamed = batch.plan([(job, None)], out, "x", batch.RENAME)[0]
    assert renamed.output == out / "x_2.mp4" and "renamed" in renamed.note
    over = batch.plan([(job, None)], out, "x", batch.OVERWRITE)[0]
    assert over.output == out / "x.mp4" and "overwrites" in over.note
    skipped = batch.plan([(job, None)], out, "x", batch.SKIP)[0]
    assert skipped.output is None and "exists" in skipped.note

    # two clips with the same name within one batch never collide, whatever the policy
    for policy in (batch.RENAME, batch.OVERWRITE, batch.SKIP):
        items = batch.plan([(job, None), (job, None)], out, "y", policy)
        assert [i.output.name for i in items] == ["y.mp4", "y_2.mp4"]


def test_plan_never_overwrites_source(src):
    job = _job(src)
    item = batch.plan([(job, None)], None, "{name}", batch.OVERWRITE)[0]
    assert item.output == src.parent / "clip_2.mp4"


def test_plan_image_sequence(src, tmp_path):
    job = _job(src, codec="png_seq")
    (tmp_path / "seq").mkdir()
    item = batch.plan([(job, None)], tmp_path, "seq", batch.RENAME)[0]
    assert item.output.parent == tmp_path / "seq_2" and item.output.name == "seq_2_%06d.png"


def test_batch_runs_all(src, tmp_path, encoder_status):
    jobs = [(_job(src, trim=Trim(0, 48)), None),
            (_job(src, codec="x264", trim=Trim(10, 30)), encoder_status["x264"].pix_fmts)]
    items = batch.plan(jobs, tmp_path / "out", "{n}", batch.RENAME)
    events = []
    result = batch.Batch(items).run(lambda i: events.append(("start", i)), None,
                                    lambda r: events.append((r.status, r.index)))
    assert [r.status for r in result.results] == ["done", "done"]
    assert events == [("start", 0), ("done", 0), ("start", 1), ("done", 1)]
    for item in items:
        assert item.output.stat().st_size > 1000


def test_batch_skip_and_failure(src, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.mp4").write_bytes(b"old")
    ok = _job(src, trim=Trim(0, 24))
    empty = _job(src, codec="x264", trim=Trim(5, 5))       # empty range → cannot be built
    items = batch.plan([(ok, None)], out, "a", batch.SKIP)
    items += batch.plan([(empty, None)], out, "b", batch.RENAME)
    result = batch.Batch(items).run()
    assert [r.status for r in result.results] == ["skipped", "failed"]
    assert "empty" in result.results[1].error
    assert (out / "a.mp4").read_bytes() == b"old"


def test_batch_cancel_deletes_partial_output(src, tmp_path):
    jobs = [(_job(src, codec="x264", speed=Fraction(1, 40), interpolation="mci"), None),
            (_job(src), None)]
    items = batch.plan(jobs, tmp_path / "out", "{n}", batch.RENAME)
    b = batch.Batch(items)
    started = threading.Event()

    def progress(i, p):
        if p.frame > 0:
            started.set()

    t = threading.Thread(target=lambda: setattr(b, "result", b.run(on_progress=progress)))
    t.start()
    assert started.wait(60)
    b.cancel()
    t.join(30)
    assert [r.status for r in b.result.results] == ["cancelled", "cancelled"]
    assert b.result.cancelled
    assert not items[0].output.exists() and not items[1].output.exists()
