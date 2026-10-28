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
   sound time-stretched by rubberband (pitch preserved, good even at 10× slower). Each piece
   is cut / padded to its exact length in samples, so every section border stays in sync.
   - rubberband (as FFmpeg runs it) moves the content ~10–18 ms of *input* time early, i.e.
     87 ms at 8× slower, 720 ms at 40× – measured once per tempo (`rubberband_lead`, a click
     through the same filter) and compensated.
   - Each piece is read with 0.5 s of sound before and after it (its own `-ss/-t` input – no
     asplit, which made FFmpeg buffer all later pieces), so rubberband works on context and is
     past its start-up at the border.
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

from . import ffmpeg_bin, segments as seg
from .formats import COPY
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


# --------------------------------------------------------------------------- rubberband lead

CONTEXT = 0.5           # seconds of real-time sound read before and after every piece
_LEAD_CACHE: dict[tuple[str, float], float] = {}


def _tempo(a: float, b: float, out: float) -> float:
    return min(max((b - a) / out, TEMPO_MIN), TEMPO_MAX) if out > 0 and b > a else 1.0


def needs_stretch(tempo: float) -> bool:
    return abs(tempo - 1) > 1e-4


def rubberband_lead(tempo: float) -> float:
    """How far rubberband moves the content early, in seconds of input (0 if unmeasurable).

    A click CONTEXT seconds into a short signal goes through `rubberband=tempo` exactly as in
    the real graph; its position in the output gives the lead. Cached per FFmpeg and tempo.
    """
    key = (ffmpeg_bin.ffmpeg(), round(tempo, 6))
    if key in _LEAD_CACHE:
        return _LEAD_CACHE[key]
    click = CONTEXT
    src = (f"aevalsrc='if(between(t,{click},{click}+0.001),0.9,0)':"
           f"s={OUT_RATE}:d={click + 0.3}:c=stereo")
    res = subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-nostdin", "-f", "lavfi", "-i", src,
                          "-af", f"rubberband=tempo={tempo:.6f}", "-ac", "1", "-f", "s16le", "-"],
                         capture_output=True, timeout=60, **ffmpeg_bin.POPEN_FLAGS)
    lead = 0.0
    if res.returncode == 0 and len(res.stdout) >= 2:
        samples = memoryview(res.stdout).cast("h")
        peak = max(range(len(samples)), key=lambda i: abs(samples[i]))
        level = abs(samples[peak])
        if level > 3000:
            # strong stretching smears the click over hundreds of ms – what the ear times is its
            # onset, so that is aligned (first sample above half the peak)
            onset = next(i for i in range(peak + 1) if abs(samples[i]) > level // 2)
            lead = click - onset / OUT_RATE * tempo
    _LEAD_CACHE[key] = lead
    return lead


# --------------------------------------------------------------------------- graph

def _sample(t: float) -> int:
    return round(t * OUT_RATE)


def plan_inputs(job: Job) -> list[tuple[float, float, str]]:
    """Per piece: (seek, duration) on the *file's* timeline for its own input, and its chain.

    The chain turns input i+1 into [p<i>]: exactly the piece's output length in samples
    (lengths come from the running total, so rounding never adds up). Assumes the sound covers
    the seek point (true for camera files: audio and video start together).
    """
    k = slowmo_factor(job)
    head = "aresample=48000"
    if k > 1.001:       # phone slow motion: back to the original pitch and real-time length
        head += f",asetrate={round(OUT_RATE * k)},aresample={OUT_RATE}"
    plans = []
    total = 0.0
    for i, (a, b, out) in enumerate(pieces(job)):
        n = _sample(total + out) - _sample(total)
        total += out
        # -ss counts from the container start (format_start), frame times are absolute
        start_file = a * k - job.info.format_start
        seek = max(0.0, start_file - CONTEXT * k)
        pre = (start_file - seek) / k                       # real-time context before the piece
        length = (start_file - seek) + (b - a + CONTEXT) * k
        chain = f"[{i + 1}:a:0]{head},asetpts=N/SR/TB"
        tempo = _tempo(a, b, out)
        if needs_stretch(tempo):
            first = (pre - rubberband_lead(tempo)) / tempo      # output time of the piece start
            chain += f",rubberband=tempo={tempo:.6f}"
            if first >= 0:
                chain += f",atrim=start_sample={_sample(first)}"
            else:
                chain += f",adelay={_sample(-first)}S:all=1"
        else:
            chain += f",atrim=start_sample={_sample(pre)}"
        chain += f",asetpts=N/SR/TB,apad=whole_len={n},atrim=end_sample={n}[p{i}]"
        plans.append((seek, length, chain))
    return plans


def filter_graph(job: Job) -> str:
    """Sound of the source (inputs 1…N, one per piece) → [aout], exactly as long as the video."""
    plans = plan_inputs(job)
    chains = [c for _, _, c in plans]
    joined = "".join(f"[p{i}]" for i in range(len(plans)))
    tail = f"{joined}concat=n={len(plans)}:v=0:a=1[aout]" if len(plans) > 1 else f"{joined}anull[aout]"
    return ";".join(chains + [tail])


def _video_tag(path: Path) -> str | None:
    res = ffmpeg_bin.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=codec_tag_string", "-of", "csv=p=0",
                          str(path)], timeout=60)
    tag = res.stdout.strip()
    return tag if tag and not tag.startswith("[") and tag != "0x0000" else None


def mux_args(job: Job, video: Path, output: Path) -> list[str]:
    args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-y", "-v", "error", "-nostdin", "-i", str(video)]
    plans = plan_inputs(job)
    for seek, length, _ in plans:
        args += ["-ss", f"{seek:.6f}", "-t", f"{length:.6f}", "-i", str(job.info.path)]
    args += ["-filter_complex", filter_graph(job),
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
