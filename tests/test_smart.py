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


def _hevc_nal(t: int, first_slice: bool = True, payload: bytes = b"\x11\x22\x33") -> bytes:
    """Annex-B HEVC NAL unit: header (type t, layer 0, temporal id 0) + first slice bit."""
    return b"\x00\x00\x01" + bytes([t << 1, 1, 0x80 if first_slice else 0x00]) + payload


def _h264_nal(t: int, first_mb0: bool = True) -> bytes:
    return b"\x00\x00\x00\x01" + bytes([0x60 | t, 0x80 if first_mb0 else 0x40]) + b"\x55\x66\x77"


def _split_everywhere(data: bytes):
    """All ways of cutting `data` into two blocks, plus 1-byte blocks."""
    yield [data]
    for i in range(1, len(data)):
        yield [data[:i], data[i:]]
    yield [data[i:i + 1] for i in range(len(data))]


def test_parse_access_units_hevc():
    # VPS/SPS/PPS, IDR in two slices, CRA, RASL, trailing picture
    stream = (_hevc_nal(32) + _hevc_nal(33) + _hevc_nal(34)
              + _hevc_nal(19) + _hevc_nal(19, first_slice=False)
              + _hevc_nal(21) + _hevc_nal(8) + _hevc_nal(1) + b"\x99" * 8)
    want = [[19, 19], [21], [8], [1]]
    for blocks in _split_everywhere(stream):
        assert list(smart.parse_access_units(blocks, hevc=True)) == want, [len(b) for b in blocks]


def test_parse_access_units_h264():
    stream = (_h264_nal(7) + _h264_nal(8) + _h264_nal(5) + _h264_nal(5, first_mb0=False)
              + _h264_nal(1) + _h264_nal(1) + b"\x99" * 8)
    want = [[5], [1], [1]]
    for blocks in _split_everywhere(stream):
        assert list(smart.parse_access_units(blocks, hevc=False)) == want


def test_access_units_reports_ffmpeg_failure(tmp_path, h264_clip):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"this is not a video" * 100)
    info = probe(h264_clip)                         # any H.264 MediaInfo
    with pytest.raises(smart.AnalysisError, match="exit code"):
        list(smart._access_units(broken, info))
    with pytest.raises(smart.AnalysisError):
        smart.join_points(broken, info, scan_frames(h264_clip))


def test_access_units_early_stop_kills_ffmpeg(h264_clip):
    info = probe(h264_clip)
    gen = smart._access_units(h264_clip, info, chunk=256)
    assert next(gen)                                # FFmpeg is running now
    gen.close()                                     # must not hang or leave FFmpeg behind


def test_join_points(h264_clip, hevc10_clip, hevc_closed_clip):
    for clip in (h264_clip, hevc_closed_clip):
        info, fm = probe(clip), scan_frames(clip)
        assert smart.join_points(clip, info, fm) == fm.keyframes      # closed GOPs: all
    info, fm = probe(hevc10_clip), scan_frames(hevc10_clip)
    assert len(fm.keyframes) > 1
    assert smart.join_points(hevc10_clip, info, fm) == [0]           # open GOP: IDR only


@pytest.mark.parametrize("fixture", ["h264_clip", "hevc10_clip", "hevc_closed_clip"])
def test_fast_join_points_match_the_full_scan(request, fixture, monkeypatch):
    """Reading only the keyframe packets gives the same join points as the whole bitstream."""
    clip = request.getfixturevalue(fixture)
    info, fm = probe(clip), scan_frames(clip)
    assert fm.packets and smart._keyframe_types(clip, info, fm) is not None   # fast path taken
    fast = smart.join_points(clip, info, fm)
    monkeypatch.setattr(smart, "_keyframe_types", lambda *a: None)          # force the fallback
    assert smart.join_points(clip, info, fm) == fast


def test_fast_path_reads_no_bitstream(h264_clip, monkeypatch):
    info, fm = probe(h264_clip), scan_frames(h264_clip)

    def forbidden(*a, **k):
        raise AssertionError("the whole bitstream was read")
    monkeypatch.setattr(smart, "_access_units", forbidden)
    monkeypatch.setattr(smart, "_decode_order_pts", forbidden)
    assert smart.join_points(h264_clip, info, fm) == fm.keyframes


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
    assert isinstance(getattr(run, "inner", run), smart.SmartRunner)    # inside the sound step
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


def test_sound_follows_the_smart_parts(h264_clip):
    """Re-encoded parts last whole frames at their rate – the sound must follow those lengths."""
    from vsc.core import audio
    job, fm = _setup(h264_clip)
    real = job.info.real_fps
    job.segments = [seg.Segment(0, 40, real * 8, reencode=True, out_fps=Fraction(25)),
                    seg.Segment(80, 90, Fraction(30), reencode=True, out_fps=Fraction(60))]
    parts = smart.plan(job, job.joins)
    # 40 frames at 8× real speed = 0.0208 s, but the part is 1 whole frame at 25 fps = 0.04 s
    assert parts[0].kind == "encode" and parts[0].duration != seg.duration(
        seg.pieces(job.segments, parts[0].start, parts[0].end, real))
    pieces = audio.pieces(job)
    k = audio.slowmo_factor(job)
    video_t, sound_t = Fraction(0), 0.0
    for part in parts:
        # sound reached at the real-time position where this part starts
        start = audio._file_time(job, part.start) / k
        sound_at = sum(out for a, b, out in pieces if b <= start + 1e-9)
        assert sound_at == pytest.approx(float(video_t), abs=1e-9), part
        video_t += part.duration
    assert sum(out for *_, out in pieces) == pytest.approx(float(video_t), abs=1e-9)


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
