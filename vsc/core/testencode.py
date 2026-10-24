"""Test encode: N output frames from the playhead with the clip's exact settings.

The measured speed and size give the time / size estimates for the whole clip and the batch.
Speed = output frames / total elapsed time of the test. Measured against full encodes this was
closer than a "steady rate + start-up" model, which came out 7–40 % too optimistic (encoder
lookahead fills before the first frame is reported). The test piece's content still matters:
an easy piece underestimates a busy clip.
"""
from __future__ import annotations

import math
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .job import Job, OutputSettings, Trim, output_path
from . import runner

DEFAULT_FRAMES = 100


@dataclass
class TestResult:
    settings: OutputSettings      # snapshot – the result is stale once the settings differ
    output: Path
    workdir: Path
    source_start: int             # first source frame of the test
    frame_ratio: float            # output frames per source frame
    frames: int                   # output frames written
    elapsed: float
    fps: float                    # output frames per second, start-up included
    bytes: int
    src_pixels: int               # per frame – to scale the result to other clips
    out_pixels: int
    ok: bool = True
    cancelled: bool = False
    error: str = ""
    commands: list[list[str]] = field(default_factory=list)   # for display

    def source_frame(self, out_frame: int) -> int:
        """Source frame shown at (or nearest to) output frame `out_frame` of the test."""
        return self.source_start + round(out_frame / self.frame_ratio)

    def estimate_seconds(self, job: Job) -> float:
        return job.output_frame_count / self.fps if self.fps > 0 else math.inf

    def estimate_bytes(self, job: Job) -> int:
        return round(self.bytes / max(1, self.frames) * job.output_frame_count)


def pixels(job: Job) -> tuple[int, int]:
    """(source, output) pixels per frame."""
    sw, sh = job.info.display_size
    ow, oh = job.output_size() if job.codec else (sw, sh)
    return sw * sh, ow * oh


def test_trim(job: Job, playhead: int, n_frames: int) -> Trim:
    """Source range that produces about n_frames output frames, starting at the playhead."""
    total = job.total_frames
    need = min(total, max(1, math.ceil(n_frames / job.frame_ratio)))
    start = max(0, min(playhead, total - need))
    if job.snaps_to_keyframes:
        start = job.frames.keyframe_at_or_before(start)
        end = job.frames.keyframe_after(min(total, start + need) - 1)  # whole GOPs, ≥ need
        return Trim(start, None if end >= total else end)
    return Trim(start, start + need)


class TestEncode:
    """One test encode. `cancel()` may be called from another thread."""

    def __init__(self, job: Job, playhead: int, n_frames: int = DEFAULT_FRAMES,
                 supported_pix_fmts: list[str] | None = None):
        self.settings = job.settings.clone()
        self.job = Job(job.info, self.settings, test_trim(job, playhead, n_frames), job.frames)
        self.workdir = Path(tempfile.mkdtemp(prefix="vsc-test-"))
        self.output = output_path(self.job, self.workdir, "test")
        self.runner = runner.create(self.job, self.output, supported_pix_fmts)

    @property
    def commands(self) -> list[list[str]]:
        describe = getattr(self.runner, "describe", None)   # RIFE: extract, rife, encode
        return describe() if describe else [self.runner.args]

    def cancel(self) -> None:
        self.runner.cancel()

    def run(self, on_progress=None) -> TestResult:
        res = self.runner.run(on_progress)
        frames = res.frames or (self.job.output_frame_count if res.ok else 0)
        out_files = [self.output] if self.output.is_file() else list(self.workdir.rglob("*.*"))
        return TestResult(
            settings=self.settings, output=self.output, workdir=self.workdir,
            source_start=self.job.trim.start, frame_ratio=self.job.frame_ratio,
            frames=frames, elapsed=res.elapsed,
            fps=frames / res.elapsed if res.elapsed > 0 else 0.0,
            bytes=sum(f.stat().st_size for f in out_files if f.is_file()),
            src_pixels=pixels(self.job)[0], out_pixels=pixels(self.job)[1], ok=res.ok, cancelled=res.cancelled,
            error=res.error, commands=self.commands)


def discard(result: TestResult | None) -> None:
    if result:
        shutil.rmtree(result.workdir, ignore_errors=True)


@dataclass
class Estimate:
    seconds: float
    bytes: int
    exact: bool          # measured on this clip with these settings (else derived)


def estimate(job: Job, own: TestResult | None, others: list[TestResult]) -> Estimate | None:
    """Time and size for `job`: from its own test, else scaled from a test with equal settings."""
    if own and own.ok and own.settings == job.settings:
        return Estimate(own.estimate_seconds(job), own.estimate_bytes(job), True)
    for r in others:
        if r.ok and r.settings == job.settings and r.fps > 0:
            # work ≈ decoded + encoded pixels; file size ≈ encoded pixels
            src_px, out_px = pixels(job)
            fps = r.fps * (r.src_pixels + r.out_pixels) / (src_px + out_px)
            per_frame = r.bytes / max(1, r.frames) * out_px / max(1, r.out_pixels)
            return Estimate(job.output_frame_count / fps,
                            round(per_frame * job.output_frame_count), False)
    return None
