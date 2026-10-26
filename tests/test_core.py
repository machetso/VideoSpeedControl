"""Core tests. Test clips are generated on first run (tests/media)."""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import pytest

from vsc.core import encoders, ffmpeg_bin, formats, preview, rife, testencode
from vsc.core import runner as runners
from vsc.core.job import Job, Mode, OutputSettings, Trim, output_path
from vsc.core.probe import probe, scan_frames
from vsc.core.runner import Runner


def _job(clip: Path, **kw) -> Job:
    info = probe(clip)
    trim = kw.pop("trim", Trim())
    return Job(info, OutputSettings(**kw), trim, scan_frames(clip, info.stream_index))


def _run(job: Job, tmp: Path, status) -> Path:
    supported = status[job.codec.key].pix_fmts if job.codec else None
    out = output_path(job, tmp)
    res = Runner(job, out, supported).run()
    assert res.ok, res.error
    return out


def _stream(path: Path) -> dict:
    res = ffmpeg_bin.run([ffmpeg_bin.ffprobe(), "-v", "error", "-count_frames",
                          "-print_format", "json", "-show_streams", str(path)])
    return json.loads(res.stdout)["streams"]


def _md5s(path: Path, extra: list[str] = ()) -> list[str]:
    res = ffmpeg_bin.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-i", str(path), "-map", "0:v",
                          *extra, "-f", "framemd5", "-"])
    return [ln.split(",")[-1].strip() for ln in res.stdout.splitlines() if not ln.startswith("#")]


# ---------------------------------------------------------------- mode decision

def test_mode_selection(h264_clip):
    assert _job(h264_clip).mode == Mode.RETIME
    j = _job(h264_clip, codec="x264")
    assert j.mode == Mode.REENCODE
    assert _job(h264_clip, codec="x264", speed=Fraction(1, 2)).mode == Mode.DROP
    assert _job(h264_clip, codec="x264", speed=Fraction(1, 20)).mode == Mode.INTERPOLATE
    j = _job(h264_clip, speed=Fraction(1, 2))
    assert j.retime_blockers() and "lossless speed" in j.retime_blockers()[0]
    j = _job(h264_clip, resize="exact", width=1920, height=1080)
    assert any("Resizing" in r for r in j.retime_blockers())


def test_keyframe_snapping(h264_clip):
    fm = _job(h264_clip).frames
    assert fm.keyframes[:3] == [0, 24, 48]
    assert fm.snap_in(30) == 24 and fm.snap_in(40) == 48
    assert fm.snap_out(500) == 504 and fm.snap_out(950) == fm.count


# ---------------------------------------------------------------- lossless retime

def test_retime_copy_trimmed(h264_clip, tmp_path, encoder_status):
    job = _job(h264_clip, fps=Fraction(50), trim=Trim(24, 504))
    out = _run(job, tmp_path, encoder_status)
    streams = _stream(out)
    assert [s["codec_type"] for s in streams] == ["video"]          # no audio
    assert int(streams[0]["nb_read_frames"]) == 480
    assert _md5s(out) == _md5s(h264_clip)[24:504]                   # untouched pictures
    times = scan_frames(out).times
    deltas = {round(b - a, 6) for a, b in zip(times, times[1:])}
    assert deltas == {0.02}                                          # exact 50 fps


def test_retime_copy_hevc_keeps_tag(hevc10_clip, tmp_path, encoder_status):
    out = _run(_job(hevc10_clip, fps=Fraction(25)), tmp_path, encoder_status)
    s = _stream(out)[0]
    assert s["codec_tag_string"] == "hvc1" and s["pix_fmt"] == "yuv420p10le"


# ---------------------------------------------------------------- re-encode

def test_reencode_frame_exact_trim(h264_clip, tmp_path, encoder_status):
    """Modes B/C cut frame-exactly: lossless FFV1 output equals source frames 30..59."""
    job = _job(h264_clip, codec="ffv1", trim=Trim(30, 60))
    out = _run(job, tmp_path, encoder_status)
    assert _md5s(out) == _md5s(h264_clip)[30:60]


@pytest.mark.parametrize("speed,interp", [
    (Fraction(1, 2), "blend"),      # drop mode
    (Fraction(1, 20), "dup"),
    (Fraction(1, 20), "blend"),
    (Fraction(1, 20), "mci"),
])
def test_speed_changes(h264_clip, tmp_path, encoder_status, speed, interp):
    job = _job(h264_clip, codec="x264", speed=speed, interpolation=interp,
               preset="ultrafast", trim=Trim(0, 48),
               resize="exact", width=640, height=360)
    out = _run(job, tmp_path, encoder_status)
    s = _stream(out)[0]
    assert int(s["nb_read_frames"]) == job.output_frame_count
    assert Fraction(s["avg_frame_rate"]) == 25


@pytest.mark.parametrize("fit,size", [("pad", (1080, 1080)), ("crop", (1080, 1080)),
                                       ("stretch", (1080, 1080))])
def test_resize_modes(h264_clip, tmp_path, encoder_status, fit, size):
    job = _job(h264_clip, codec="x264", preset="ultrafast", resize="exact",
               width=size[0], height=size[1], fit=fit, trim=Trim(0, 10))
    s = _stream(_run(job, tmp_path, encoder_status))[0]
    assert (s["width"], s["height"]) == size
    assert s.get("sample_aspect_ratio", "1:1") in ("1:1", "N/A")


def test_fit_box_keeps_aspect(h264_clip):
    job = _job(h264_clip, codec="x264", resize="fit_box", width=1080, height=1920)
    assert job.output_size() == (1080, 608)


CODEC_CASES = [
    ("ffv1", None, "444", 10, "yuv444p10le"),
    ("utvideo", None, "422", 8, "yuv422p"),
    ("magicyuv", None, "420", 8, "yuv420p"),
    ("ffvhuff", None, "420", 10, "yuv420p10le"),
    ("huffyuv", None, "422", 8, "yuv422p"),
    ("x264_lossless", None, "420", 8, "yuv420p"),
    ("x265_lossless", None, "420", 10, "yuv420p10le"),
    ("qtrle", None, "444", 8, "rgb24"),
    ("x264", None, "422", 10, "yuv422p10le"),
    ("x265", None, "444", 8, "yuv444p"),
    ("svtav1", None, "420", 10, "yuv420p10le"),
    ("vp9", None, "420", 8, "yuv420p"),
    ("prores", "proxy", "422", 10, "yuv422p10le"),
    ("prores", "4444", "444", 10, "yuv444p10le"),
    ("dnxhr", "sq", "422", 8, "yuv422p"),
    ("dnxhr", "hqx", "422", 10, "yuv422p10le"),
    ("cineform", None, "422", 10, "yuv422p10le"),
    ("mjpeg", None, "420", 8, "yuvj420p"),
]


@pytest.mark.parametrize("codec,profile,chroma,depth,pix", CODEC_CASES)
def test_codecs(h264_clip, tmp_path, encoder_status, codec, profile, chroma, depth, pix):
    preset = {"x265_lossless": "ultrafast", "x265": "ultrafast", "svtav1": "12", "vp9": "5"}
    job = _job(h264_clip, codec=codec, profile=profile, chroma=chroma, depth=depth,
               preset=preset.get(codec), trim=Trim(0, 12),
               resize="exact", width=640, height=360)
    assert job.output_format(encoder_status[codec].pix_fmts)[2] == pix
    s = _stream(_run(job, tmp_path, encoder_status))[0]
    # FFmpeg's ProRes decoder reports 4444 as 12-bit; the encoder input was 10-bit
    assert s["pix_fmt"] == ("yuv444p12le" if profile == "4444" else pix)
    assert int(s["nb_read_frames"]) == job.output_frame_count


@pytest.mark.parametrize("codec", ["png_seq", "dpx_seq", "tiff_seq", "exr_seq"])
def test_image_sequences(h264_clip, tmp_path, encoder_status, codec):
    job = _job(h264_clip, codec=codec, depth=10, trim=Trim(0, 6),
               resize="exact", width=320, height=180)
    out = _run(job, tmp_path, encoder_status)
    assert len(list(out.parent.iterdir())) == job.output_frame_count


def test_unsupported_format_falls_back(h264_clip, encoder_status):
    """SVT-AV1 is 4:2:0 only – asking for 4:4:4 picks the closest possible format."""
    job = _job(h264_clip, codec="svtav1", chroma="444", depth=10)
    assert job.output_format(encoder_status["svtav1"].pix_fmts)[:2] == ("420", 10)


# ---------------------------------------------------------------- trimming rules

def test_trim_rules(h264_clip):
    copy_job = _job(h264_clip)                                  # mode A: keyframes every 24
    assert copy_job.snaps_to_keyframes
    assert copy_job.trim_with_in(30) == Trim(24, None)
    copy_job.trim = Trim(24, None)
    assert copy_job.trim_with_out(500) == Trim(24, 504)         # last frame 500 → end 504
    copy_job.trim = Trim(24, 504)
    assert copy_job.trim_with_in(600) == Trim(600, None)        # in after out drops out
    assert copy_job.trim_with_out(5) == Trim(0, 24)             # out before in resets in

    enc = _job(h264_clip, codec="x264", trim=Trim(30, 61))      # frame-exact
    assert not enc.snaps_to_keyframes
    assert enc.trim_with_in(31) == Trim(31, 61)
    assert enc.trim_with_out(enc.total_frames + 5) == Trim(30, None)
    assert enc.snapped_trim() == Trim(24, 72)


# ---------------------------------------------------------------- preview frames

def _decoded_frame(path: Path, index: int, size) -> bytes:
    """Reference: decode from the start and pick frame `index` by number."""
    res = subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-i", str(path), "-vf",
                          f"select=eq(n\\,{index}),scale={size[0]}:{size[1]}:flags=bilinear,setsar=1",
                          "-frames:v", "1", "-c:v", "bmp", "-pix_fmt", "bgr24",
                          "-f", "image2pipe", "-"], capture_output=True, check=True)
    return res.stdout


@pytest.mark.parametrize("index", [0, 30, 501, 958])
def test_grab_exact_frame(h264_clip, index):
    info = probe(h264_clip)
    fm = scan_frames(h264_clip, info.stream_index)
    size = preview.fit_size(info, 320, 320)
    assert size == (320, 180)
    assert preview.grab_frame(info, fm, index, size) == _decoded_frame(h264_clip, index, size)


def test_thumbnails_are_keyframes(h264_clip):
    info = probe(h264_clip)
    fm = scan_frames(h264_clip, info.stream_index)
    picks = preview.thumbnail_frames(fm, 10)
    assert len(picks) == 10 and all(p in fm.keyframes for p in picks)
    size = (160, 90)
    fast = preview.grab_frame(info, fm, 30, size, accurate=False)
    assert fast == preview.grab_frame(info, fm, 24, size)


# ---------------------------------------------------------------- test encode / estimates

def test_test_encode_and_estimate(h264_clip, hevc10_clip, encoder_status):
    job = _job(h264_clip, codec="x264", preset="ultrafast", speed=Fraction(1, 20),
               interpolation="blend", resize="exact", width=640, height=360)
    supported = encoder_status["x264"].pix_fmts
    assert testencode.test_trim(job, 955, 20) == Trim(949, 959)        # shifted back at the end
    t = testencode.TestEncode(job, playhead=100, n_frames=20, supported_pix_fmts=supported)
    res = t.run()
    try:
        assert res.ok and res.frames == 21 and res.source_start == 100  # 10 src → 21 out
        assert res.bytes > 0 and res.fps > 0
        assert res.source_frame(0) == 100 and res.source_frame(20) == 110
        assert _stream(res.output)[0]["nb_read_frames"] == "21"
        est = testencode.estimate(job, res, [])
        assert est.exact and est.seconds > 0
        assert est.bytes == round(res.bytes / 21 * job.output_frame_count)

        job.settings.quality = 30                                     # stale → no estimate
        assert testencode.estimate(job, res, []) is None
        job.settings.quality = None
        other = _job(hevc10_clip, codec="x264", preset="ultrafast", speed=Fraction(1, 20),
                     interpolation="blend", resize="exact", width=640, height=360)
        derived = testencode.estimate(other, None, [res])
        assert derived and not derived.exact
    finally:
        testencode.discard(res)
    assert not res.workdir.exists()


def test_test_encode_copy_mode(h264_clip):
    job = _job(h264_clip, fps=Fraction(50))
    t = testencode.TestEncode(job, playhead=30, n_frames=30)
    assert (t.job.trim.start, t.job.trim.end) == (24, 72)              # whole GOPs
    res = t.run()
    try:
        assert res.ok and res.frames == 48
    finally:
        testencode.discard(res)


# ---------------------------------------------------------------- RIFE

needs_rife = pytest.mark.skipif(not rife.detect().available, reason="RIFE / Vulkan not available")


def test_rife_plan_is_exact(h264_clip):
    job = _job(h264_clip, codec="x264", speed=Fraction(1, 20), interpolation="rife")
    ratio = rife.grid_ratio(job)                       # 25 / (240000/1001 · 1/20) = 1001/480
    exact = Fraction(25) / (job.info.fps / 20)
    assert ratio.denominator < exact.denominator and abs(float(ratio / exact) - 1) <= 5e-4
    pieces = rife.plan(job, ratio, src_per_piece=ratio.denominator * 3)
    assert len(pieces) > 1
    assert sum(p.keep for p in pieces) == job.output_frame_count
    k = 0
    for p in pieces:
        assert p.files * ratio == p.n                   # rife spacing == 1/ratio exactly
        for i in range(p.keep):                         # global grid continues across pieces
            assert p.start + Fraction(i) / ratio == Fraction(k) / ratio
            k += 1
        last = p.start + Fraction(p.keep - 1) / ratio
        assert int(last) + 1 < p.start + p.files        # blend partner is a real input file

    two = _job(h264_clip, codec="x264", fps=Fraction(24000, 1001), speed=Fraction(1, 20),
               interpolation="rife")
    assert rife.grid_ratio(two) == 2                   # 239.76 → 23.976 at 1/20: exactly 2×


def _psnr(a: bytes, b: bytes) -> float:
    a, b = a[54:], b[54:]                               # skip BMP headers
    mse = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
    return 99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse)


@needs_rife
def test_rife_encode(h264_clip, tmp_path, encoder_status):
    supported = encoder_status["x264"].pix_fmts
    outputs = {}
    for method in ("rife", "dup"):          # dup = the plain ffmpeg pipeline as reference
        job = _job(h264_clip, codec="x264", preset="ultrafast", quality=12,
                   fps=Fraction(24000, 1001), speed=Fraction(1, 20), interpolation=method,
                   resize="exact", width=320, height=180, trim=Trim(100, 130))
        runner = runners.create(job, output_path(job, tmp_path, method), supported)
        assert isinstance(runner, rife.RifeRunner) == (method == "rife")
        res = runner.run()
        assert res.ok, res.error
        assert int(_stream(res.output)[0]["nb_read_frames"]) == job.output_frame_count == 60
        outputs[method] = (probe(res.output), scan_frames(res.output))
    # ratio is exactly 2: every even output frame is a real source frame. Same picture and
    # colours as the ffmpeg pipeline (a wrong YUV↔RGB matrix would drop this far below 35 dB)
    for k in (0, 20, 58):
        got = preview.grab_frame(*outputs["rife"], k, (320, 180))
        want = preview.grab_frame(*outputs["dup"], k, (320, 180))
        assert _psnr(got, want) > 37, k
    assert not list(Path(tempfile.gettempdir()).glob("vsc-rife-*"))   # temp files removed


# ---------------------------------------------------------------- recording metadata

def test_recording_metadata(tmp_path):
    """Device, date, capture rate (phone slow-mo) and audio from the container tags."""
    phone = tmp_path / "phone.mp4"
    subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=320x240:r=30000/1001:d=1", "-f", "lavfi", "-i", "sine=d=1",
                    "-c:v", "libx264", "-c:a", "aac", "-ac", "2", "-shortest",
                    "-movflags", "use_metadata_tags",
                    "-metadata", "com.android.manufacturer=Google",
                    "-metadata", "com.android.model=Pixel 10 Pro",
                    "-metadata", "com.android.capture.fps=240.000000",
                    "-metadata", "creation_time=2026-10-25T09:12:21.000000Z", str(phone)],
                   check=True)
    i = probe(phone)
    assert i.device == "Google Pixel 10 Pro"
    assert i.recorded.isoformat().startswith("2026-10-25") and i.recorded.utcoffset() is not None
    assert i.recorded.timestamp() == 1792919541
    assert i.capture_fps == 240 and round(i.slowmo_factor, 2) == 8.01
    assert i.audio.startswith("aac stereo")

    gopro = tmp_path / "gopro.mp4"
    subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=320x240:r=240:d=0.2", "-c:v", "libx264",
                    "-movflags", "use_metadata_tags", "-metadata", "firmware=H23.01.02.32.00", "-metadata:s:v",
                    "handler_name=GoPro H.265", str(gopro)], check=True)
    g = probe(gopro)
    assert g.device == "GoPro HERO12 (firmware H23.01.02.32.00)"
    assert g.slowmo_factor is None and g.audio is None


def test_playback_plan_real_fps(h264_clip):
    from vsc.core import playback
    from vsc.core.job import Job, OutputSettings
    from vsc.core.probe import probe
    info = probe(h264_clip)
    info.capture_fps = info.fps * 8          # pretend phone slow-mo: file plays 8× slower
    job = Job(info, OutputSettings(fps=info.fps))
    assert job.lossless_speed == Fraction(1, 8) and job.is_lossless_speed
    plan = playback.plan(job, 0, (320, 180))
    assert plan.frame_ratio == pytest.approx(1) and plan.source_frame(10) == 10
    assert any("fps=" in a for a in plan.args)
