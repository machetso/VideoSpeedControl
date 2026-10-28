# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Sound: stretched or compressed to the new video length, the pitch stays the same.

1. Phone slow motion stores its sound slowed down like a tape (lower pitch – measured on a
   Pixel: hardly any energy above 3 kHz). Resampled to 48 kHz, then `asetrate` × slow-mo factor
   brings it back to the original pitch and real-time length (independent of the source rate).
   Normal clips are real time already.
2. Every run of frames with one speed (the whole trim, or each speed section) gets its piece of
   sound time-stretched by Sonic (`vsc.core.sonic`, pitch preserved) – the same algorithm as the
   Android version; the user chose it after listening to rubberband, Rubber Band R3 and
   Signalsmith Stretch. Each piece is cut / padded to its exact length in samples (running
   total, so nothing drifts over sections).
   - Each piece is decoded with CONTEXT seconds before and after it (its own `-ss/-t` FFmpeg
     run), so Sonic is past its start-up at the border.
   - Sonic moves the content a few ms of input early; measured per tempo with a click
     (`sonic.lead`) and compensated.
3. The pieces are written to a temporary WAV, and the sound is added to the finished video in
   a last step (video stream copied) – this works the same for every processing mode, and a
   lossless video stays lossless.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

from . import ffmpeg_bin, segments as seg, sonic
from .formats import COPY
from .job import Job
from .runner import Result

OUT_RATE = 48000
TEMPO_MIN, TEMPO_MAX = 0.01, 20.0           # Sonic: ≤ 100× slower (build patch), ≤ 20× faster
# audio codec per container (None = this container takes no sound)
CODEC_ARGS = {
    "mp4": ["-c:a", "aac", "-b:a", "192k"],
    "mov": ["-c:a", "aac", "-b:a", "192k"],
    "mkv": ["-c:a", "aac", "-b:a", "192k"],
    "webm": ["-c:a", "libopus", "-b:a", "160k"],
    "avi": ["-c:a", "pcm_s16le"],
    "mxf": ["-c:a", "pcm_s24le"],
}


def unavailable_reason(job: Job) -> str | None:
    """Why this output gets no sound (None = it can)."""
    if not job.info.has_audio:
        return "This clip has no sound."
    if reason := sonic.unavailable_reason():
        return reason
    if job.codec and job.codec.image_sequence:
        return "Image sequences cannot hold sound."
    if job.codec and job.codec.external:
        return "FFmpeg cannot handle AV2 yet, so the AV2 file stays without sound."
    if job.container not in CODEC_ARGS:
        return f"{job.container.upper()} files cannot hold sound."
    return None


def wanted(job: Job) -> bool:
    return job.settings.audio and unavailable_reason(job) is None


def slowmo_factor(job: Job) -> float:
    """How much the file's sound is slowed down (phone slow motion), else 1."""
    return float(job.info.real_fps / job.info.fps)


def _file_time(job: Job, frame: int) -> float:
    """Start of source frame `frame` on the file's timeline (end of the clip for frame = count)."""
    fm = job.frames
    if fm is None or fm.count == 0:
        return frame / float(job.info.fps)
    if frame < fm.count:
        return fm.times[frame]
    last = fm.times[-1] - fm.times[-2] if fm.count > 1 else 1 / float(job.info.fps)
    return fm.times[-1] + last


def pieces(job: Job) -> list[tuple[float, float, float]]:
    """(start, end, output length) in seconds of *real-time* sound for every run of one speed.

    Smart re-encode: re-encoded parts last a whole number of frames at their own rate
    (`smart.plan`), so their pieces are scaled to the part's real duration.
    """
    k = slowmo_factor(job)
    if job.settings.smart:
        out = []
        for part in job.smart_parts():
            ps = seg.pieces(job.segments, part.start, part.end, job.info.real_fps)
            scale = Fraction(part.duration) / seg.duration(ps) if part.kind == "encode" else 1
            out += [(_file_time(job, p.start) / k, _file_time(job, p.end) / k,
                     float(Fraction(p.end - p.start) / p.rate * scale)) for p in ps]
        return out
    if job.has_segments:
        out = [(_file_time(job, p.start) / k, _file_time(job, p.end) / k,
                float(Fraction(p.end - p.start) / p.rate)) for p in job.pieces()]
        if job.settings.codec != COPY:
            # re-encoded video lasts a whole number of frames – the sound ends exactly with it
            a, b, last = out[-1]
            video = job.output_frame_count / float(job.settings.fps)
            out[-1] = (a, b, max(0.0, last + video - sum(o for *_, o in out)))
        return out
    start, end = job.trim.start, job.trim_end
    return [(_file_time(job, start) / k, _file_time(job, end) / k, job.output_duration)]


# --------------------------------------------------------------------------- rendering

CONTEXT = 0.25          # seconds of real-time sound decoded before and after every piece
CHANNELS = 2


class AudioError(Exception):
    """Decoding or stretching the sound failed."""


def _tempo(a: float, b: float, out: float) -> float:
    return min(max((b - a) / out, TEMPO_MIN), TEMPO_MAX) if out > 0 and b > a else 1.0


def needs_stretch(tempo: float) -> bool:
    return abs(tempo - 1) > 1e-4


def _sample(t: float) -> int:
    return round(t * OUT_RATE)


def _head(job: Job) -> str:
    k = slowmo_factor(job)
    head = f"aresample={OUT_RATE}"
    if k > 1.001:       # phone slow motion: back to the original pitch and real-time length
        head += f",asetrate={round(OUT_RATE * k)},aresample={OUT_RATE}"
    return head


def plan(job: Job) -> list[dict]:
    """Per piece: what to decode (seek / length on the file's timeline), the context before it,
    its tempo and its exact output length in samples (from the running total)."""
    k = slowmo_factor(job)
    out, total = [], 0.0
    for a, b, length in pieces(job):
        n = _sample(total + length) - _sample(total)
        total += length
        # -ss counts from the container start (format_start), frame times are absolute
        start_file = a * k - job.info.format_start
        seek = max(0.0, start_file - CONTEXT * k)
        out.append({"seek": seek, "length": (start_file - seek) + (b - a + CONTEXT) * k,
                    "pre": (start_file - seek) / k, "tempo": _tempo(a, b, length), "samples": n})
    return out


def _decode(job: Job, seek: float, length: float) -> bytes:
    """Real-time sound of the source from `seek` for `length` seconds (file timeline):
    interleaved s16, 48 kHz, stereo. Assumes the sound covers the seek point (camera files)."""
    res = subprocess.run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-nostdin",
                          "-ss", f"{seek:.6f}", "-t", f"{length:.6f}", "-i", str(job.info.path),
                          "-map", "0:a:0", "-af", _head(job), "-ac", str(CHANNELS),
                          "-ar", str(OUT_RATE), "-f", "s16le", "-"],
                         capture_output=True, timeout=600, **ffmpeg_bin.POPEN_FLAGS)
    if res.returncode != 0:
        raise AudioError("Decoding the sound failed: "
                         + res.stderr.decode("utf-8", "replace").strip()[-500:])
    return res.stdout


def render_piece(job: Job, p: dict) -> bytes:
    """One piece, exactly p["samples"] frames long."""
    fb = 2 * CHANNELS
    pcm = _decode(job, p["seek"], p["length"])
    n, tempo = p["samples"], p["tempo"]
    if needs_stretch(tempo):
        with sonic.Stream(OUT_RATE, CHANNELS, tempo) as s:
            s.write(pcm)
            stretched = s.read() + s.flush()
        first = (p["pre"] - sonic.lead(OUT_RATE, tempo, CONTEXT)) / tempo   # piece start in output
        skip = _sample(first)
        data = stretched[skip * fb:] if skip >= 0 else bytes(-skip * fb) + stretched
    else:
        data = pcm[_sample(p["pre"]) * fb:]
    data = data[:n * fb]
    return data + bytes(n * fb - len(data))            # a short result is padded with silence


def render(job: Job, wav: Path, cancelled=lambda: False) -> bool:
    """Write the whole sound of `job` to `wav` (s16, 48 kHz, stereo). False if cancelled."""
    import wave
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(OUT_RATE)
        for p in plan(job):
            if cancelled():
                return False
            w.writeframes(render_piece(job, p))
    return True


def _video_tag(path: Path) -> str | None:
    res = ffmpeg_bin.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=codec_tag_string", "-of", "csv=p=0",
                          str(path)], timeout=60)
    tag = res.stdout.strip()
    return tag if tag and not tag.startswith("[") and tag != "0x0000" else None


def mux_args(job: Job, video: Path, sound: Path, output: Path) -> list[str]:
    args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-y", "-v", "error", "-nostdin",
            "-i", str(video), "-i", str(sound), "-map", "0:v", "-map", "1:a", "-c:v", "copy"]
    if job.container in ("mp4", "mov") and video.exists() and (tag := _video_tag(video)):
        args += ["-tag:v", tag]              # keep hvc1 (Apple) / hev1 (smart) as written
    return args + CODEC_ARGS[job.container] + [str(output)]


class AudioRunner:
    """Runs the video runner into a temporary file, then adds the sound to the real output."""

    def __init__(self, inner, job: Job, video: Path, output: Path):
        self.inner, self.job, self.video, self.output = inner, job, video, output
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    @property
    def args(self) -> list[str]:
        return self.inner.args

    def describe(self) -> list[list[str]]:
        describe = getattr(self.inner, "describe", None)
        return (describe() if describe else [self.inner.args]) + \
            [mux_args(self.job, self.video, temp_sound_path(self.output), self.output)]

    def cancel(self) -> None:
        self._cancelled = True
        self.inner.cancel()
        proc = self._proc
        if proc and proc.poll() is None:
            proc.kill()

    def run(self, on_progress=None) -> Result:
        start = time.monotonic()
        res = self.inner.run(on_progress)
        if not res.ok or self._cancelled:
            self.video.unlink(missing_ok=True)
            return Result(ok=False, cancelled=res.cancelled or self._cancelled,
                          output=self.output, elapsed=time.monotonic() - start,
                          frames=res.frames, error=res.error)
        sound = temp_sound_path(self.output)
        try:
            if not render(self.job, sound, lambda: self._cancelled):
                raise AudioError("cancelled")
        except Exception as e:  # noqa: BLE001 – reported on the result
            self.video.unlink(missing_ok=True)
            sound.unlink(missing_ok=True)
            return Result(ok=False, cancelled=self._cancelled, output=self.output,
                          elapsed=time.monotonic() - start, frames=res.frames,
                          error="" if self._cancelled else f"Preparing the sound failed: {e}")
        err: deque[str] = deque(maxlen=30)
        self._proc = proc = subprocess.Popen(
            mux_args(self.job, self.video, sound, self.output), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace",
            **ffmpeg_bin.POPEN_FLAGS)
        t = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
        t.start()
        proc.wait()
        t.join(timeout=2)
        self.video.unlink(missing_ok=True)
        sound.unlink(missing_ok=True)
        ok = proc.returncode == 0 and not self._cancelled
        if not ok and self.output.exists():
            self.output.unlink(missing_ok=True)
        return Result(ok=ok, cancelled=self._cancelled, output=self.output,
                      elapsed=time.monotonic() - start, frames=res.frames,
                      error="" if ok else "Adding the sound failed: " + "".join(err).strip())


def temp_sound_path(output: Path) -> Path:
    """Where the stretched sound is written before it is added (same folder as the output)."""
    return output.with_name(f"{output.stem}.sound-{os.getpid()}.wav")


def temp_video_path(output: Path) -> Path:
    """Where the video is written before the sound is added (same folder, same extension)."""
    return output.with_name(f"{output.stem}.video-{os.getpid()}{output.suffix}")
