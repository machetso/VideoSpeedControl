# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Convert videos, pro mode and smart settings (2026-11-04): container / sound rules, jobs,
the CRF search, real conversions (sound copied / re-encoded), a VMAF measurement, the window."""
from __future__ import annotations

import os
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # never real windows (desktop may set wayland)

from vsc.core import audio, batch, command, convert, suggest  # noqa: E402
from vsc.core.convert import ConvertSettings  # noqa: E402
from vsc.core.job import Mode  # noqa: E402
from vsc.core.probe import probe, scan_frames  # noqa: E402

from conftest import _make  # noqa: E402


@pytest.fixture(scope="session")
def divx_clip() -> Path:
    """Like the user's DivX cartoons: AVI, MPEG-4 part 2, 10 fps, 368×208, MP3 22.05 kHz."""
    return _make("divx_10fps.avi", [
        "-f", "lavfi", "-i", "testsrc2=s=368x208:r=10:d=3",
        "-f", "lavfi", "-i", "sine=f=440:d=3:sample_rate=22050", "-c:v", "mpeg4",
        "-vtag", "XVID", "-q:v", "4", "-c:a", "libmp3lame", "-ac", "2", "-b:a", "96k",
        "-shortest"])


@pytest.fixture(scope="session")
def divx_info(divx_clip):
    return probe(divx_clip), scan_frames(divx_clip)


def _available(status, key):
    return status.get(key) is not None and status[key].available


# --------------------------------------------------------------------------- rules

def test_probe_reads_sound_details(divx_info):
    info, _ = divx_info
    assert (info.audio_codec, info.audio_channels, info.audio_rate) == ("mp3", 2, 22050)
    assert 90_000 <= info.audio_bitrate <= 100_000
    assert info.video_bitrate and info.video_bitrate > 0


def test_container_rules():
    assert audio.container_holds("mp4", "mp3") and audio.container_holds("mp4", "aac")
    assert not audio.container_holds("mov", "opus") and not audio.container_holds("mov", "flac")
    assert audio.container_holds("mkv", "dts") and audio.container_holds("mkv", "mp3")
    assert not audio.container_holds("mp4", None)
    assert convert.containers_for("svtav1") == ["mp4", "mkv"]          # FFmpeg: no AV1 in MOV
    assert convert.containers_for("x265") == ["mp4", "mov", "mkv"]


def test_audio_problems(divx_info):
    info, _ = divx_info
    ok = ConvertSettings(codec="x264", container="mp4", audio="copy")
    assert convert.audio_problem(info, ok) is None
    assert "MP3" in convert.audio_problem(info, ok.copy(container="mov", audio="opus")) \
        or "Opus" in convert.audio_problem(info, ok.copy(container="mov", audio="opus"))
    assert convert.audio_problem(info, ok.copy(audio="smart")) is None


def test_pro_job_frame_rate_keeps_length(divx_info):
    info, frames = divx_info
    job = convert.make_pro_job(info, frames, ConvertSettings(codec="x264", fps=Fraction(25)))
    assert float(job.speed) == 1.0 and job.output_frame_count == 75
    assert abs(job.output_duration - 3.0) < 1e-9
    assert job.mode in (Mode.INTERPOLATE, Mode.DROP) and job.settings.interpolation == "dup"
    same = convert.make_pro_job(info, frames, ConvertSettings(codec="x264"))
    assert same.mode == Mode.REENCODE and same.output_frame_count == 30


def test_bitrate_replaces_quality(divx_info, tmp_path):
    info, frames = divx_info
    job = convert.make_pro_job(info, frames, ConvertSettings(codec="aom", rate="kbps", kbps=300))
    args = command.encode_args(job, tmp_path / "x.mp4")
    assert "-crf" not in args and args[args.index("-b:v") + 1] == "300k"
    assert args.count("-b:v") == 1                    # libaom's "-b:v 0" is gone
    q = convert.make_pro_job(info, frames, ConvertSettings(codec="aom", rate="crf", crf=40))
    args = command.encode_args(q, tmp_path / "x.mp4")
    assert args[args.index("-crf") + 1] == "40" and args[args.index("-b:v") + 1] == "0"


def test_channels_never_above_the_source(divx_info):
    info, frames = divx_info
    job = convert.make_pro_job(info, frames, ConvertSettings(codec="x264", audio="aac", channels=6))
    assert job.settings.audio_channels == 2
    mono = convert.make_pro_job(info, frames, ConvertSettings(codec="x264", audio="aac", channels=1,
                                                              audio_kbps=64))
    assert audio.direct(mono) and audio.codec_args(mono) == [
        "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "22050"]


def test_smart_needs_a_measurement(divx_info):
    info, frames = divx_info
    with pytest.raises(ValueError):
        convert.make_pro_job(info, frames, ConvertSettings(rate="smart"))
    s = suggest.Suggestion("svtav1", "identical", 33, 100, 96.5, "copy", None, 2, 1000)
    job = convert.make_pro_job(info, frames, ConvertSettings(rate="smart", audio="smart"), s)
    assert job.settings.quality == 33 and job.settings.audio_codec == "copy"


def test_describe():
    text = convert.describe(ConvertSettings(codec="x265", container="mkv", fps=Fraction(25),
                                            rate="kbps", kbps=800, audio="aac", channels=1,
                                            audio_kbps=64))
    assert text == "HEVC / H.265 MKV · 25 fps · 800 kbit/s · AAC mono 64k"


# --------------------------------------------------------------------------- smart logic

def test_search_finds_the_highest_value():
    assert suggest.search(10, 50, lambda q: q <= 31) == (31, True)
    assert suggest.search(10, 50, lambda q: True) == (50, True)
    assert suggest.search(10, 50, lambda q: False) == (10, False)


def test_goals():
    assert suggest.meets("identical", [96.5, 95.0, 97.0])
    assert not suggest.meets("identical", [99.0, 99.0, 94.0])       # one sample too low
    assert not suggest.meets("identical", [95.9, 95.9])             # mean too low
    assert suggest.meets("smaller", [94.0, 92.0])


def test_audio_suggestions(divx_info):
    info, _ = divx_info
    assert suggest.suggest_audio(info, "mp4", "identical") == ("copy", None, 2)
    assert suggest.suggest_audio(info, "webm", "identical") == ("aac", 80, 2)    # 96 × 0.85
    from dataclasses import replace
    ac3 = replace(info, audio_codec="ac3", audio_channels=6, audio_bitrate=384_000)
    assert suggest.suggest_audio(ac3, "mov", "identical") == ("copy", None, 6)
    pcm = replace(info, audio_codec="pcm_s16le", audio_bitrate=1_411_000)
    assert suggest.suggest_audio(pcm, "mp4", "identical") == ("aac", 192, 2)
    assert suggest.suggest_audio(pcm, "mp4", "smaller") == ("aac", 104, 2)
    silent = replace(info, has_audio=False)
    assert suggest.suggest_audio(silent, "mp4", "identical") == ("none", None, None)


def test_sample_spans(divx_info):
    info, frames = divx_info
    assert suggest.sample_spans(info, frames) == [(0, 30)]          # short: the whole clip
    from dataclasses import replace
    long = replace(info, nb_frames=6000)
    spans = suggest.sample_spans(long, None)
    assert len(spans) == 3 and all(n == 150 for _, n in spans)
    assert spans[0][0] < spans[1][0] < spans[2][0] < 6000 - 150


# --------------------------------------------------------------------------- real runs

def _convert(job, folder):
    items = convert.plan([(job, None)], folder)
    result = batch.Batch(items).run()
    assert result.count("done") == 1, result.results
    return items[0].output


def test_mkv_25fps_sound_copied(divx_info, tmp_path):
    info, frames = divx_info
    cs = ConvertSettings(codec="x264", container="mkv", fps=Fraction(25), rate="kbps", kbps=400,
                         audio="copy")
    out = _convert(convert.make_pro_job(info, frames, cs), tmp_path)
    assert out.suffix == ".mkv"
    o = probe(out)
    assert (o.codec, o.fps, o.audio_codec, o.audio_rate, o.audio_channels) == \
        ("h264", 25, "mp3", 22050, 2)
    assert scan_frames(out).count == 75 and abs(o.duration - 3.0) < 0.15


def test_mp4_sound_mono_aac(divx_info, tmp_path):
    info, frames = divx_info
    cs = ConvertSettings(codec="x264", container="mp4", audio="aac", channels=1, audio_kbps=64)
    o = probe(_convert(convert.make_pro_job(info, frames, cs), tmp_path))
    assert (o.audio_codec, o.audio_channels, o.audio_rate) == ("aac", 1, 22050)
    assert abs(o.duration - 3.0) < 0.15


def test_measure_divx(divx_info, encoder_status):
    if not suggest.vmaf_available():
        pytest.skip("no VMAF in this FFmpeg")
    key = "svtav1" if _available(encoder_status, "svtav1") else "x264"
    info, frames = divx_info
    seen = []
    s = suggest.suggest(info, frames, key, "identical", "mp4",
                        progress=lambda f, t: seen.append(f))
    lo, hi = suggest.crf_range(key)
    assert lo <= s.crf <= hi and s.audio == "copy" and s.video_kbps > 0
    assert s.vmaf >= suggest.GOALS["identical"][0] or s.note
    assert seen and seen[-1] == 1.0
    smaller = suggest.suggest(info, frames, key, "smaller", "mp4")
    assert smaller.crf >= s.crf


# --------------------------------------------------------------------------- the window

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp())
    return QApplication.instance() or QApplication([])


def _wait(qapp, condition, timeout=30.0):
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "timed out"
        qapp.processEvents()
        time.sleep(0.01)


def test_dialog_pro_own_settings(qapp, divx_clip, tmp_path):
    import shutil
    from vsc.gui.convert_dialog import ConvertDialog
    for name in ("a.avi", "b.avi"):
        shutil.copy(divx_clip, tmp_path / name)
    d = ConvertDialog()
    d.pro_radio.setChecked(True)
    assert d.add_paths([tmp_path]) == 2
    _wait(qapp, lambda: all(r.info for r in d.rows))
    ed = d.editor
    ed.codec.setCurrentIndex(ed.codec.findData("x265"))
    ed.rate.setCurrentIndex(ed.rate.findData("kbps"))
    assert d.general.codec == "x265" and d.general.rate == "kbps"
    assert d.table.item(0, 3).text() == "General – not measured yet"     # sound: smart
    ed.audio.setCurrentIndex(ed.audio.findData("aac"))
    assert d.table.item(0, 3).text() == "General"
    # own settings for the second video
    d.table.selectRow(1)
    d._make_own()
    assert d.rows[1].own is not None and d.settings_box.title().startswith("Own settings")
    ed.container.setCurrentIndex(ed.container.findData("mov"))
    ed.audio.setCurrentIndex(ed.audio.findData("opus"))     # not allowed in MOV → falls back
    assert ed.audio.currentData() == "aac"
    ed.audio.setCurrentIndex(ed.audio.findData("copy"))      # MP3 into MOV: allowed
    assert d.rows[1].own.container == "mov" and d.rows[1].own.audio == "copy"
    assert d.rows[0].own is None and d.general.container == "mp4"
    assert d.table.item(1, 3).text().startswith("Own: HEVC / H.265 MOV")
    assert d.start_button.isEnabled()
    jobs = d._jobs_for([0, 1])
    assert [j.container for j, _ in jobs] == ["mp4", "mov"]
    # AV1 cannot go into MOV: the container switches
    ed.codec.setCurrentIndex(ed.codec.findData("svtav1"))
    assert d.rows[1].own.container == "mp4"
    d._drop_own()
    assert d.rows[1].own is None and d.settings_box.title().startswith("General")
    # easy mode ignores own settings and offers the smart switch
    d.easy_radio.setChecked(True)
    assert not ed.container.isVisibleTo(d) and ed.smart.isVisibleTo(d)
    ed.smart.setChecked(True)
    assert d.easy_settings.measures and d.measure_button.isVisibleTo(d)
    assert "will be measured first" in d.summary.text()
    d.close()
