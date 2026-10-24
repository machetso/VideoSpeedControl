"""Run an ffmpeg command and report progress."""
from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import command, ffmpeg_bin
from .job import Job


@dataclass
class Progress:
    frame: int
    total_frames: int
    fps: float            # processing speed in output frames per second
    elapsed: float
    eta: float | None

    @property
    def fraction(self) -> float:
        return min(1.0, self.frame / self.total_frames) if self.total_frames else 0.0


@dataclass
class Result:
    ok: bool
    cancelled: bool
    output: Path
    elapsed: float
    frames: int
    error: str = ""

    @property
    def fps(self) -> float:
        return self.frames / self.elapsed if self.elapsed > 0 else 0.0


class Runner:
    """Runs one job. `cancel()` may be called from another thread."""

    def __init__(self, job: Job, output: Path, supported_pix_fmts: list[str] | None = None):
        self.job = job
        self.output = output
        self.args = command.build(job, output, supported_pix_fmts)
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.stdin.write("q")   # lets ffmpeg finish the file cleanly
                proc.stdin.flush()
            except (OSError, ValueError):
                pass
            threading.Timer(3.0, lambda: proc.poll() is None and proc.kill()).start()

    def run(self, on_progress: Callable[[Progress], None] | None = None) -> Result:
        total = self.job.output_frame_count
        self.output.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        self._proc = proc = subprocess.Popen(
            self.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1, **ffmpeg_bin.POPEN_FLAGS,
        )
        stderr_lines: deque[str] = deque(maxlen=40)
        err_thread = threading.Thread(
            target=lambda: stderr_lines.extend(proc.stderr), daemon=True)
        err_thread.start()

        frame = 0
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "frame" and value.isdigit():
                frame = int(value)
            elif key == "progress" and on_progress:
                elapsed = time.monotonic() - start
                fps = frame / elapsed if elapsed > 0 else 0.0
                eta = (total - frame) / fps if fps > 0 else None
                on_progress(Progress(frame, total, fps, elapsed, eta))
        proc.wait()
        err_thread.join(timeout=2)
        elapsed = time.monotonic() - start

        ok = proc.returncode == 0 and not self._cancelled
        error = "" if ok else "\n".join(l.rstrip() for l in stderr_lines).strip()
        return Result(ok=ok, cancelled=self._cancelled, output=self.output,
                      elapsed=elapsed, frames=frame, error=error)


def create(job: Job, output: Path, supported_pix_fmts: list[str] | None = None):
    """The right runner for a job: RIFE interpolation runs its own pipeline."""
    from . import rife   # rife imports this module
    if rife.is_rife(job):
        return rife.RifeRunner(job, output, supported_pix_fmts)
    return Runner(job, output, supported_pix_fmts)
