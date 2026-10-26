# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Batch export: output names, overwrite policy and running the clips one after another.

No Qt here – the GUI runs `Batch.run` in a worker thread and turns the events into signals.
Jobs are snapshots: settings changed while the batch runs do not affect it.
"""
from __future__ import annotations

import re
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import runner
from .command import CommandError
from .formats import COPY
from .job import Job, output_path

DEFAULT_PATTERN = "{name}_{speed}x_{fps}fps"

PATTERN_TOKENS = {
    "{name}": "source file name without extension",
    "{speed}": "speed factor, e.g. 0_1",
    "{slower}": "how many times slower, e.g. 10",
    "{fps}": "output frame rate, e.g. 25",
    "{codec}": "output codec, e.g. x264 or copy",
    "{res}": "output size, e.g. 1920x1080",
    "{mode}": "processing: lossless, smart or reencode",
    "{n}": "position in the queue, 01, 02 …",
}

# Overwrite policies
RENAME, OVERWRITE, SKIP = "rename", "overwrite", "skip"
POLICIES = (
    (RENAME, "Add a number (name_2, name_3 …)"),
    (OVERWRITE, "Overwrite"),
    (SKIP, "Skip the clip"),
)

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _num(v: float) -> str:
    return f"{v:.3g}".replace(".", "_")


def mode_key(job: Job) -> str:
    if job.settings.smart:
        return "smart"
    return "lossless" if job.settings.codec == COPY else "reencode"


def describe(job: Job) -> str:
    """Short description of what an export of `job` does, e.g. 'Smart, 3 sections (1 re-encoded)'."""
    n = sum(1 for s in job.segments if s.start < job.trim_end and s.end > job.trim.start)
    sections = f", {n} section{'s' * (n != 1)}" if n else ""
    if job.settings.smart:
        enc = sum(1 for s in job.segments if s.reencode and s.start < job.trim_end
                  and s.end > job.trim.start)
        return f"Smart{sections} ({enc} re-encoded)" if n else "Smart (copy)"
    if job.settings.codec == COPY:
        return f"Lossless{sections}" if n else \
            f"Lossless @ {float(job.settings.fps):.5g} fps"
    return f"Re-encode {job.codec.label.split(' (')[0]} @ {float(job.settings.fps):.5g} fps{sections}"


def render_name(pattern: str, job: Job, index: int = 1) -> str:
    """File name (without extension) for `job`; unknown {tokens} are left as they are."""
    w, h = job.output_size() if job.codec else job.info.display_size
    values = {
        "name": job.info.path.stem,
        "speed": _num(float(job.speed)),
        "slower": _num(1 / float(job.speed)),
        "fps": f"{float(job.settings.fps):.5g}".replace(".", "_"),
        "codec": job.settings.codec,
        "res": f"{w}x{h}",
        "mode": mode_key(job),
        "n": f"{index:02d}",
    }
    name = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), pattern)
    name = _UNSAFE.sub("_", name).strip(" .")
    return name or job.info.path.stem


def _target(path: Path) -> Path:
    """What has to be free on disk: the file, or the folder of an image sequence."""
    return path.parent if "%" in path.name else path


@dataclass
class Item:
    job: Job                          # snapshot
    output: Path | None               # None = skipped
    supported_pix_fmts: list[str] | None = None
    note: str = ""                    # why skipped / renamed / overwritten

    @property
    def target(self) -> Path | None:
        return _target(self.output) if self.output else None


def plan(jobs: list[tuple[Job, list[str] | None]], folder: Path | None, pattern: str,
         policy: str) -> list[Item]:
    """Output path for every job. `folder` None = next to each source file.

    Names are unique within the batch too, and a source file is never overwritten.
    """
    items: list[Item] = []
    taken: set[Path] = set()
    sources = {job.info.path for job, _ in jobs}
    for index, (job, pix_fmts) in enumerate(jobs, 1):
        out_dir = folder or job.info.path.parent
        name = render_name(pattern, job, index)
        path, note, n = output_path(job, out_dir, name), "", 1
        # Another output of this batch or a source file: always renamed, whatever the policy.
        while _target(path) in taken or _target(path) in sources:
            n += 1
            path, note = output_path(job, out_dir, f"{name}_{n}"), f"renamed (_{n})"
        if _target(path).exists():
            if policy == SKIP:
                items.append(Item(job, None, pix_fmts, f"skipped: {_target(path).name} exists"))
                continue
            if policy == OVERWRITE:
                note = "overwrites the existing file"
            else:
                while _target(path).exists() or _target(path) in taken:
                    n += 1
                    path, note = output_path(job, out_dir, f"{name}_{n}"), f"renamed (_{n})"
        items.append(Item(job, path, pix_fmts, note))
        taken.add(_target(path))
    return items


# --------------------------------------------------------------------------- running

@dataclass
class ItemResult:
    index: int
    status: str                 # "done" | "failed" | "cancelled" | "skipped"
    output: Path | None
    elapsed: float = 0.0
    frames: int = 0
    error: str = ""


@dataclass
class BatchResult:
    results: list[ItemResult] = field(default_factory=list)
    cancelled: bool = False

    def count(self, status: str) -> int:
        return sum(r.status == status for r in self.results)


class Batch:
    """Runs the items one after another. `cancel()` may be called from another thread.

    Incomplete outputs (failed or cancelled clips) are deleted, so every file that remains
    is a finished one.
    """

    def __init__(self, items: list[Item]):
        self.items = items
        self._runner = None
        self._cancelled = False
        self._lock = threading.Lock()

    @property
    def total_frames(self) -> int:
        return sum(it.job.output_frame_count for it in self.items if it.output)

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            if self._runner:
                self._runner.cancel()

    def run(self, on_start: Callable[[int], None] | None = None,
            on_progress: Callable[[int, runner.Progress], None] | None = None,
            on_done: Callable[[ItemResult], None] | None = None) -> BatchResult:
        result = BatchResult()

        def finish(r: ItemResult) -> None:
            result.results.append(r)
            if on_done:
                on_done(r)

        for index, item in enumerate(self.items):
            if item.output is None:
                finish(ItemResult(index, "skipped", None, error=item.note))
                continue
            if self._cancelled:
                finish(ItemResult(index, "cancelled", item.output))
                continue
            if on_start:
                on_start(index)
            target_existed = item.target.exists()
            try:
                with self._lock:
                    if self._cancelled:
                        raise _Cancelled
                    self._runner = runner.create(item.job, item.output, item.supported_pix_fmts)
                res = self._runner.run(
                    (lambda p, i=index: on_progress(i, p)) if on_progress else None)
            except _Cancelled:
                finish(ItemResult(index, "cancelled", item.output))
                continue
            except (CommandError, ValueError, OSError) as e:
                finish(ItemResult(index, "failed", item.output, error=str(e)))
                continue
            finally:
                with self._lock:
                    self._runner = None
            if res.ok:
                finish(ItemResult(index, "done", item.output, res.elapsed, res.frames))
                continue
            if not target_existed or item.target.is_file():
                _remove(item.target)       # a half-written file is worse than none
            status = "cancelled" if res.cancelled else "failed"
            finish(ItemResult(index, status, item.output, res.elapsed, res.frames, res.error))
        result.cancelled = self._cancelled
        return result


class _Cancelled(Exception):
    pass


def _remove(target: Path) -> None:
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    else:
        target.unlink(missing_ok=True)
