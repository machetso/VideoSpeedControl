# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Sound: stretched or compressed to the new video length, the pitch stays the same.

1. Phone slow motion stores its sound slowed down like a tape (lower pitch – measured on a
   Pixel: hardly any energy above 3 kHz). `asetrate` × slow-mo factor brings it back to the
   original pitch and real-time length. Normal clips are real time already.
2. Every run of frames with one speed (the whole trim, or each speed section) gets its piece of
   sound time-stretched by rubberband (pitch preserved, good even at 10× slower), then the
   pieces are joined and padded / cut to the exact video length.
3. The sound is added to the finished video in a last step (video stream copied), so this works
   the same for every processing mode – a lossless video stays lossless.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

from . import ffmpeg_bin
from .job import Job
from .runner import Result

OUT_RATE = 48000
TEMPO_MIN, TEMPO_MAX = 0.01, 100.0          # rubberband's range
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
    """(start, end, output length) in seconds of *real-time* sound for every run of one speed."""
    k = slowmo_factor(job)
    if job.has_segments or job.settings.smart:
        return [(_file_time(job, p.start) / k, _file_time(job, p.end) / k,
                 float(Fraction(p.end - p.start) / p.rate)) for p in job.pieces()]
    start, end = job.trim.start, job.trim_end
    return [(_file_time(job, start) / k, _file_time(job, end) / k, job.output_duration)]


def filter_graph(job: Job) -> str:
    """Sound of the source (input 1) → [aout], exactly as long as the output video."""
    rate = job.info.audio_rate or OUT_RATE
    k = slowmo_factor(job)
    head = "[1:a:0]"
    if k > 1.001:       # phone slow motion: back to the original pitch and real-time length
        head += f"asetrate={round(rate * k)},aresample={OUT_RATE},"
    else:
        head += f"aresample={OUT_RATE},"
    ps = pieces(job)
    chains = []
    for i, (a, b, out) in enumerate(ps):
        chain = f"[s{i}]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS"
        if out > 0 and b > a:
            tempo = (b - a) / out
            if abs(tempo - 1) > 1e-4:
                chain += f",rubberband=tempo={min(max(tempo, TEMPO_MIN), TEMPO_MAX):.6f}"
        chains.append(chain + f"[p{i}]")
    total = job.output_duration
    split = f"asplit={len(ps)}" + "".join(f"[s{i}]" for i in range(len(ps))) if len(ps) > 1 \
        else "anull[s0]"
    joined = "".join(f"[p{i}]" for i in range(len(ps)))
    tail = (f"{joined}concat=n={len(ps)}:v=0:a=1," if len(ps) > 1 else f"{joined}anull,")
    tail += f"apad=whole_dur={total:.6f},atrim=end={total:.6f}[aout]"
    return ";".join([head + split] + chains + [tail])


def _video_tag(path: Path) -> str | None:
    res = ffmpeg_bin.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=codec_tag_string", "-of", "csv=p=0",
                          str(path)], timeout=60)
    tag = res.stdout.strip()
    return tag if tag and not tag.startswith("[") and tag != "0x0000" else None


def mux_args(job: Job, video: Path, output: Path) -> list[str]:
    args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-y", "-v", "error", "-nostdin",
            "-i", str(video), "-i", str(job.info.path),
            "-filter_complex", filter_graph(job),
            "-map", "0:v", "-map", "[aout]", "-c:v", "copy"]
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
            [mux_args(self.job, self.video, self.output)]

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
        err: deque[str] = deque(maxlen=30)
        self._proc = proc = subprocess.Popen(
            mux_args(self.job, self.video, self.output), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace",
            **ffmpeg_bin.POPEN_FLAGS)
        t = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
        t.start()
        proc.wait()
        t.join(timeout=2)
        self.video.unlink(missing_ok=True)
        ok = proc.returncode == 0 and not self._cancelled
        if not ok and self.output.exists():
            self.output.unlink(missing_ok=True)
        return Result(ok=ok, cancelled=self._cancelled, output=self.output,
                      elapsed=time.monotonic() - start, frames=res.frames,
                      error="" if ok else "Adding the sound failed: " + "".join(err).strip())


def temp_video_path(output: Path) -> Path:
    """Where the video is written before the sound is added (same folder, same extension)."""
    return output.with_name(f"{output.stem}.video-{os.getpid()}{output.suffix}")
