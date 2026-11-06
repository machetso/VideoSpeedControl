# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Smart conversion settings (user request 2026-11-04): the smallest file that keeps the
picture and the sound of the original – measured, not guessed.

Picture: a few short samples of the file are encoded at different quality values (CRF) of the
chosen codec and compared with the original by VMAF (Netflix's perceptual score, 0–100, in the
bundled FFmpeg). A binary search finds the highest CRF – the smallest file – that still meets
the goal. Measured at the file's own size: calibrated on the user's DivX cartoons (368×208),
where VMAF upscaled to 1080p rated even 800 kbit/s AV1 below 95 although a 2× zoom showed no
difference at ~160 kbit/s (upscaled VMAF counts the removed DivX block noise as a loss).

Sound: copied when the container can hold it (nothing lost, smallest); otherwise AAC with the
same channels and sample rate at a data rate matched to the source's codec.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import audio, command, ffmpeg_bin, formats
from .probe import FrameMap, MediaInfo
from ..i18n import N_, tr

# goal → (VMAF mean over all samples, VMAF mean every single sample must reach)
GOALS = {"identical": (96.0, 94.5), "smaller": (93.0, 91.0)}
GOAL_LABELS = {"identical": N_("Looks identical"), "smaller": N_("Smaller, minimal loss")}
SAMPLES = 3
PIXEL_BUDGET = 1.5e8          # pixels per sample (sample frames = budget / frame size, clamped)
MIN_SAMPLE_FRAMES, MAX_SAMPLE_FRAMES = 48, 150
NO_SAVING = 0.95              # suggestion ≥ 95 % of the source's video rate = "no real saving"

# sound: AAC data rate relative to the source's, by source codec (AAC is about as efficient
# as MP3 at 0.85×, far more than AC-3 / DTS / MP2; Opus / Vorbis are more efficient than AAC)
AUDIO_FACTOR = {"mp3": 0.85, "mp2": 0.6, "ac3": 0.6, "eac3": 0.75, "dts": 0.5,
                "aac": 1.0, "opus": 1.25, "vorbis": 1.15, "wmav2": 0.85, "wmav1": 0.85}
LOSSLESS_KBPS_PER_CHANNEL = {"identical": 96, "smaller": 64}


class SuggestError(Exception):
    """Measuring failed (FFmpeg error, no VMAF in this FFmpeg build …)."""


@dataclass
class Suggestion:
    codec: str
    goal: str
    crf: int
    video_kbps: int           # expected average for the whole file
    vmaf: float               # mean over the samples at `crf`
    audio: str                # "copy" | "aac" | "none"
    audio_kbps: int | None    # None for copy / none
    channels: int | None
    size_bytes: int           # expected size of the whole file
    note: str = ""

    def summary(self, info: MediaInfo) -> str:
        """e.g. 'quality 23 ≈ 205 kbit/s, sound copied → about 46 % of the original'."""
        sound = {"copy": tr("sound copied"), "none": tr("no sound")}.get(
            self.audio) or tr("AAC %d kbit/s", self.audio_kbps)
        share = self.size_bytes / info.size_bytes * 100 if info.size_bytes else 0
        text = tr("quality %d ≈ %d kbit/s (VMAF %.1f), %s → about %.0f %% of the original",
                  self.crf, self.video_kbps, self.vmaf, sound, share)
        return text + (f". {self.note}" if self.note else "")


def vmaf_available() -> bool:
    res = ffmpeg_bin.run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-filters"], timeout=30)
    return " libvmaf " in res.stdout


# --------------------------------------------------------------------------- sound

def suggest_audio(info: MediaInfo, container: str, goal: str) -> tuple[str, int | None, int | None]:
    """(mode, kbit/s, channels): copy if the container holds the source's sound, else AAC."""
    if not info.has_audio:
        return "none", None, None
    if audio.container_holds(container, info.audio_codec):
        return "copy", None, info.audio_channels
    ch = min(info.audio_channels or 2, audio.MAX_CHANNELS["aac"])
    src = (info.audio_bitrate or 0) // 1000
    factor = AUDIO_FACTOR.get(info.audio_codec or "")
    if src and factor:
        kbps = src * factor
    else:                                   # PCM / FLAC / unknown: generous per channel
        kbps = LOSSLESS_KBPS_PER_CHANNEL[goal] * ch
    if goal == "smaller":
        kbps *= 0.8
    floor = 32 if ch == 1 else 48 + 24 * (ch - 2)
    kbps = max(floor, min(512, int(round(kbps / 8) * 8)))
    return "aac", kbps, ch


# --------------------------------------------------------------------------- picture

def sample_spans(info: MediaInfo, frames: FrameMap | None) -> list[tuple[int, int]]:
    """(first frame, frame count) of each sample: SAMPLES spans at 20 / 50 / 80 % of the file,
    sized by PIXEL_BUDGET; a short file is one sample of (up to) all of it."""
    total = frames.count if frames else info.frame_count
    per = int(PIXEL_BUDGET / max(1, info.width * info.height * SAMPLES))
    per = max(MIN_SAMPLE_FRAMES, min(MAX_SAMPLE_FRAMES, per))
    if total <= per * SAMPLES:
        return [(0, min(total, per * SAMPLES))]
    spans = []
    for k in range(SAMPLES):
        mid = int(total * (k + 1) / (SAMPLES + 1))
        start = max(0, min(total - per, mid - per // 2))
        spans.append((start, per))
    return spans


def crf_range(codec_key: str) -> tuple[int, int]:
    """CRF values searched: a bit below 'Visually lossless' up to 'Small file'."""
    values = formats.QUALITY_VALUES.get(codec_key)
    codec = formats.CODECS_BY_KEY[codec_key]
    if not values or codec.quality is None:
        raise SuggestError(tr("%s has no quality scale to search.", tr(codec.label)))
    lo = max(codec.quality.minimum + 1, values[0] - 8)
    return lo, min(codec.quality.maximum, values[-1])


def _run(args: list[str], cwd: Path) -> None:
    res = subprocess.run(args, cwd=cwd, capture_output=True, text=True, errors="replace",
                         timeout=3600, **ffmpeg_bin.POPEN_FLAGS)
    if res.returncode != 0:
        raise SuggestError(res.stderr.strip()[-400:] or tr("FFmpeg failed"))


def _reference(info: MediaInfo, frames: FrameMap | None, span: tuple[int, int], out: Path) -> None:
    """The sample, decoded once into lossless FFV1 – encodes and VMAF both start from it."""
    start, count = span
    t = (frames.times[start] if frames and frames.count > start else start / float(info.fps))
    t -= info.format_start
    _run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-nostdin", "-y",
          "-ss", f"{max(0.0, t):.6f}", "-i", str(info.path), "-map", f"0:{info.stream_index}",
          "-frames:v", str(count), "-an", "-c:v", "ffv1", "-level", "3", out.name], out.parent)


def _encode(job, ref: Path, out: Path, pix_fmt: str) -> int:
    args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-nostdin", "-y",
            "-i", ref.name, "-map", "0:v", "-pix_fmt", pix_fmt]
    args += command.encode_args(job, Path(out.name))
    _run(args, out.parent)
    return out.stat().st_size


def _vmaf(enc: Path, ref: Path, pix_fmt: str) -> list[float]:
    """Per-frame VMAF of `enc` against `ref`, both at the file's own size."""
    fmt = "yuv420p10le" if "10" in pix_fmt or "12" in pix_fmt else "yuv420p"
    graph = (f"[0:v]setpts=PTS-STARTPTS,format={fmt}[a];[1:v]setpts=PTS-STARTPTS,format={fmt}[b];"
             f"[a][b]libvmaf=n_threads={os.cpu_count() or 4}:log_fmt=json:log_path=vmaf.json")
    _run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-nostdin", "-i", enc.name,
          "-i", ref.name, "-lavfi", graph, "-f", "null", "-"], enc.parent)
    data = json.loads((enc.parent / "vmaf.json").read_text())
    return [f["metrics"]["vmaf"] for f in data["frames"]]


def meets(goal: str, per_sample: list[float]) -> bool:
    """Do the sample means reach the goal (overall mean and every single sample)?"""
    overall, each = GOALS[goal]
    return bool(per_sample) and sum(per_sample) / len(per_sample) >= overall \
        and min(per_sample) >= each


def search(lo: int, hi: int, ok) -> tuple[int, bool]:
    """Highest value in [lo, hi] for which ok(value) is True (quality falls as the value
    rises). Returns (value, found) – (lo, False) when even `lo` misses."""
    if not ok(lo):
        return lo, False
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if ok(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo, True


def suggest(info: MediaInfo, frames: FrameMap | None, codec_key: str, goal: str = "identical",
            container: str = "mp4", supported_pix_fmts: list[str] | None = None,
            progress=lambda fraction, text: None, cancelled=lambda: False) -> Suggestion:
    """Measure `info` and return the smart settings for `codec_key` and `goal`."""
    from .convert import ConvertSettings, make_pro_job       # convert imports nothing from here
    if goal not in GOALS:
        raise ValueError(f"unknown goal {goal!r}")
    lo, hi = crf_range(codec_key)
    spans = sample_spans(info, frames)
    steps = len(spans) * (1 + 7)          # references + ~log2(range) encodes each
    done = 0

    def step(text: str) -> None:
        nonlocal done
        if cancelled():
            raise SuggestError("cancelled")
        done += 1
        progress(min(0.99, done / steps), text)

    with tempfile.TemporaryDirectory(prefix="vsc-suggest-") as tmp:
        d = Path(tmp)
        refs = []
        for k, span in enumerate(spans):
            step(tr("Preparing sample %d of %d", k + 1, len(spans)))
            ref = d / f"ref{k}.mkv"
            _reference(info, frames, span, ref)
            refs.append(ref)
        base = make_pro_job(info, frames, ConvertSettings(codec=codec_key, rate="crf", crf=lo,
                                                          audio="none", container="mkv"))
        _, _, pix_fmt = base.output_format(supported_pix_fmts)
        results: dict[int, tuple[list[float], int]] = {}

        def measure(crf: int) -> tuple[list[float], int]:
            if crf not in results:
                job = make_pro_job(info, frames, ConvertSettings(codec=codec_key, rate="crf",
                                                                 crf=crf, audio="none",
                                                                 container="mkv"))
                scores, size = [], 0
                for k, ref in enumerate(refs):
                    step(tr("Trying quality %d (sample %d)", crf, k + 1))
                    enc = d / f"enc{k}.mkv"
                    size += _encode(job, ref, enc, pix_fmt)
                    per_frame = _vmaf(enc, ref, pix_fmt)
                    scores.append(sum(per_frame) / len(per_frame))
                results[crf] = (scores, size)
            return results[crf]

        crf, found = search(lo, hi, lambda q: meets(goal, measure(q)[0]))
        scores, size = measure(crf)

    seconds = sum(n for _, n in spans) / float(info.fps)
    video_kbps = max(1, round(size * 8 / seconds / 1000))
    a_mode, a_kbps, channels = suggest_audio(info, container, goal)
    sound_kbps = (info.audio_bitrate or 0) / 1000 if a_mode == "copy" else (a_kbps or 0)
    total = int((video_kbps + sound_kbps) * 1000 / 8 * info.duration)
    note = ""
    if not found:
        note = tr("Even the best quality searched does not reach the goal (VMAF %.1f).",
                  sum(scores) / len(scores))
    elif info.video_bitrate and video_kbps * 1000 >= NO_SAVING * info.video_bitrate:
        note = tr("No real saving with this codec: it needs about as much data as the original.")
    progress(1.0, tr("Measured"))
    return Suggestion(codec_key, goal, crf, video_kbps, sum(scores) / len(scores), a_mode,
                      a_kbps, channels, total, note)
