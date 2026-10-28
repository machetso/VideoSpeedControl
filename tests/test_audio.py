# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Sound: stretched to the video length with the pitch preserved (pure tones, zero crossings)."""
from __future__ import annotations

import array
import subprocess
from fractions import Fraction

import pytest

from vsc.core import audio, ffmpeg_bin, runner, segments as seg
from vsc.core.formats import COPY
from vsc.core.job import Job, OutputSettings, Trim, output_path
from vsc.core.probe import probe, scan_frames


def _durations(path) -> dict[str, float]:
    out = subprocess.run([ffmpeg_bin.ffprobe(), "-v", "error", "-show_entries",
                          "stream=codec_type,duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.split()
    return {kind: float(d) for kind, d in (line.split(",") for line in out)}


def _frequency(path, start: float, length: float) -> float:
    """Main frequency of the sound from start to start+length (mono, zero crossings)."""
    pcm = subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-ss", str(start), "-t", str(length),
                          "-i", str(path), "-map", "0:a", "-ac", "1", "-ar", "48000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    samples = array.array("h", pcm)
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0))
    return crossings / 2 / (len(samples) / 48000)


def _job(clip, **settings) -> Job:
    return Job(probe(clip), OutputSettings(**settings), Trim(), scan_frames(clip))


def test_slower_keeps_pitch_and_length(h264_clip, tmp_path):
    job = _job(h264_clip, codec=COPY, fps=Fraction(25))         # 240 → 25 fps: 9.6× slower
    assert audio.wanted(job)
    out = output_path(job, tmp_path)
    res = runner.create(job, out).run()
    assert res.ok, res.error
    d = _durations(out)
    assert d["audio"] == pytest.approx(job.output_duration, abs=0.05)
    assert d["video"] == pytest.approx(job.output_duration, abs=0.1)
    assert _frequency(out, 10, 5) == pytest.approx(440, rel=0.02)   # the source tone


def test_sections_follow_the_video(h264_clip, tmp_path):
    job = _job(h264_clip, codec="x264", fps=Fraction(50), preset="ultrafast")
    real = job.info.real_fps
    job.segments = [seg.Segment(0, 240, real * 4), seg.Segment(480, 720, Fraction(30))]
    out = output_path(job, tmp_path)
    res = runner.create(job, out).run()
    assert res.ok, res.error
    assert _durations(out)["audio"] == pytest.approx(job.output_duration, abs=0.05)
    slow_start = float(seg.output_time(job.pieces(), 480))
    assert _frequency(out, slow_start + 1, 4) == pytest.approx(440, rel=0.02)   # 8× slower part


def test_sound_ends_with_the_reencoded_video(h264_clip):
    """Re-encoded video lasts whole frames – the sound pieces must add up to exactly that."""
    job = _job(h264_clip, codec="x264", fps=Fraction(30))
    job.segments = [seg.Segment(10, 47, Fraction(70))]          # 37 frames at 70 fps: not whole
    total = sum(out for *_, out in audio.pieces(job))
    assert job.output_duration != job.output_frame_count / 30
    assert total == pytest.approx(job.output_frame_count / 30, abs=1e-9)


def _click_onsets(path, times: list[float], search: float = 0.4) -> list[float]:
    """Onset (first sample above half the local peak) of the click nearest each expected time."""
    pcm = subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-i", str(path), "-map", "0:a",
                          "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    s = array.array("h", pcm)
    out = []
    for t in times:
        lo, hi = max(0, int((t - search) * 48000)), min(len(s), int((t + search) * 48000))
        peak = max(range(lo, hi), key=lambda k: abs(s[k]))
        onset = next(k for k in range(lo, peak + 1) if abs(s[k]) > abs(s[peak]) // 2)
        out.append(onset / 48000)
    return out


@pytest.mark.parametrize("slow", [(8, 4, 2), (40, 10, 20)])
def test_section_borders_stay_in_sync(tmp_path, slow):
    """Every click must be heard when its frame is shown – also after several sections.

    Source: 240 fps with a click every 0.5 s (every 120 frames) over a quiet tone. Real-time
    parts must be exact (no drift from earlier sections). In stretched parts rubberband smears a
    click over up to ~250 ms; its onset is compensated to within a few ms, the rest of the
    spread (AAC, content-dependent transient detection) lands late, which the ear tolerates
    far better than early sound (ITU-R BT.1359: early from ~45 ms, late from ~125 ms).
    """
    clip = tmp_path / "clicks.mp4"
    subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=160x90:r=240:d=4", "-f", "lavfi", "-i",
                    "aevalsrc='if(lt(mod(t,0.5),0.0005)*gt(t,0.1),0.9,0)+0.02*sin(2*PI*300*t)'"
                    ":s=48000:d=4",
                    "-c:v", "libx264", "-g", "24", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", str(clip)], check=True)
    job = _job(clip, codec=COPY, fps=Fraction(240))
    a, b, c = (Fraction(240, x) for x in slow)
    job.segments = [seg.Segment(100, 340, a), seg.Segment(400, 560, b), seg.Segment(700, 760, c)]
    out = output_path(job, tmp_path / "out")
    res = runner.create(job, out).run()
    assert res.ok, res.error
    ps = job.pieces()
    frames = list(range(120, 960, 120))
    want = [float(seg.output_time(ps, f)) for f in frames]
    got = _click_onsets(out, want)
    report = []
    for f, w, g in zip(frames, want, got):
        rate = next(p.rate for p in ps if p.start <= f < p.end)
        err = g - w
        report.append(f"frame {f} ({float(240 / rate):g}× slower): {err * 1000:+.1f} ms")
        if rate == 240:
            assert abs(err) < 0.002, report             # real time: exact, no drift
        else:
            # stretched: onset compensated; the content-dependent rest grows with the stretch
            # but stays below the ~125 ms at which late sound becomes noticeable
            assert -0.020 < err < 0.040 + 0.0015 * float(240 / rate), report
    assert _durations(out)["audio"] == pytest.approx(job.output_duration, abs=0.03)


@pytest.mark.parametrize("rate_known", [True, False])
def test_phone_slowmo_sound_is_restored(tmp_path, rate_known):
    """A phone stores slow motion like a slowed tape: 440 Hz becomes 55 Hz at 8× slow-mo.

    The source is 44.1 kHz; the restore must not depend on knowing that (it used to assume
    48 kHz when the rate was unknown – wrong pitch).
    """
    clip = tmp_path / "phone.mp4"
    subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=320x180:r=30:d=8", "-f", "lavfi", "-i", "sine=f=55:d=8",
                    "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-movflags", "use_metadata_tags",
                    "-metadata", "com.android.capture.fps=240.000000", "-shortest", str(clip)],
                   check=True)
    job = _job(clip, codec=COPY, fps=Fraction(240))             # real time
    assert job.info.slowmo_factor == pytest.approx(8, rel=0.01)
    assert job.info.audio_rate == 44100
    if not rate_known:
        job.info.audio_rate = None
    out = output_path(job, tmp_path / "out")
    res = runner.create(job, out).run()
    assert res.ok, res.error
    assert _durations(out)["audio"] == pytest.approx(1.0, abs=0.05)
    assert _frequency(out, 0.2, 0.6) == pytest.approx(440, rel=0.03)   # original pitch again


def test_no_sound_when_off_or_impossible(h264_clip, hevc10_clip, tmp_path):
    job = _job(h264_clip, codec=COPY, fps=Fraction(240), audio=False)
    assert not audio.wanted(job)
    res = runner.create(job, output_path(job, tmp_path)).run()
    assert res.ok and "audio" not in _durations(res.output)
    assert "no sound" in audio.unavailable_reason(_job(hevc10_clip))
    assert "Image sequences" in audio.unavailable_reason(_job(h264_clip, codec="png_seq"))
    assert "AV2" in audio.unavailable_reason(_job(h264_clip, codec="av2", container="webm"))
    webm = _job(h264_clip, codec="vp9", container="webm")
    assert audio.wanted(webm) and audio.CODEC_ARGS["webm"][1] == "libopus"
