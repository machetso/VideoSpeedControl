"""AV2 via the AVM reference software – tiny pictures only, the encoder is extremely slow."""
from __future__ import annotations

from fractions import Fraction

import pytest

from vsc.core import avm, encoders, runner, testencode
from vsc.core.job import Job, OutputSettings, Trim, output_path
from vsc.core.probe import probe, scan_frames

pytestmark = pytest.mark.skipif(avm.find() is None or avm.find("avmdec") is None,
                                reason="AVM not installed (tools/fetch_avm.py)")


def _job(clip, **kw) -> Job:
    s = OutputSettings(fps=Fraction(25), resize="fit_box", width=160, height=90, **kw)
    return Job(probe(clip), s, Trim(0, 6), scan_frames(clip))


def test_detected():
    status = encoders.detect()["av2"]
    assert status.available and "yuv420p10le" in status.pix_fmts


@pytest.mark.parametrize("container", ["ivf", "webm"])
def test_encode_and_decode(h264_clip, tmp_path, container):
    job = _job(h264_clip, codec="av2", container=container, quality=200)
    run = runner.create(job, output_path(job, tmp_path))
    assert isinstance(run, avm.AvmRunner)
    progress = []
    res = run.run(progress.append)
    assert res.ok, res.error
    assert res.output.suffix == "." + container and res.output.stat().st_size > 0
    preview = tmp_path / "preview.mkv"
    avm.decode_for_preview(res.output, preview)
    info = probe(preview)
    assert info.display_size == (160, 90)
    assert scan_frames(preview).count == job.output_frame_count == 6


def test_lossless_10bit(hevc10_clip, tmp_path):
    job = _job(hevc10_clip, codec="av2_lossless", depth=10, chroma="444")
    res = runner.create(job, output_path(job, tmp_path)).run()
    assert res.ok, res.error
    preview = tmp_path / "p.mkv"
    avm.decode_for_preview(res.output, preview)
    i = probe(preview)
    assert (i.chroma, i.bit_depth) == ("444", 10)


def test_test_encode_is_capped_and_previewable(h264_clip):
    job = _job(h264_clip, codec="av2", quality=200)
    job.trim = Trim()
    test = testencode.TestEncode(job, 0, 100)
    assert test.job.source_frame_count <= 50       # 5 output frames at 25 fps from 240 fps
    result = test.run()
    try:
        assert result.ok, result.error
        assert result.frames <= testencode.EXTERNAL_MAX_FRAMES
        assert result.preview and result.preview.is_file()
    finally:
        testencode.discard(result)


def test_rife_not_allowed(h264_clip, tmp_path):
    job = _job(h264_clip, codec="av2", interpolation="rife")
    job.settings.speed = Fraction(1, 100)           # slower than lossless → interpolation
    assert job.mode.value == "interpolate"
    with pytest.raises(ValueError):
        runner.create(job, output_path(job, tmp_path))
