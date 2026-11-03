# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Convert videos (user request 2026-11-03): re-encode many files with the same codec and
quality, nothing else changed – every frame once at the file's own frame rate, source size,
sound kept – into MP4. Meant for old collections (AVI / DivX / Xvid …) as well as phone clips.

No Qt here: the GUI (`gui/convert_dialog.py`) probes the files, builds the jobs with
`make_job` and runs them with `batch.Batch`.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import batch, formats
from .job import Job, OutputSettings
from .probe import FrameMap, MediaInfo

# codecs offered (best default first); the GUI greys out the ones FFmpeg lacks
CODECS = ("svtav1", "aom", "x265", "x264")
DEFAULT_CODEC = "svtav1"            # user choice 2026-11-03: AV1 in MP4
DEFAULT_LEVEL = 1                   # index in formats.QUALITY_LEVELS: "High"
CONTAINER = "mp4"
FOLDER_NAME = "Converted"           # default: a sub-folder next to the originals

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".divx", ".xvid", ".wmv", ".asf", ".flv",
    ".mpg", ".mpeg", ".mpe", ".m2v", ".vob", ".ts", ".mts", ".m2ts", ".mxf", ".3gp", ".3g2",
    ".ogv", ".dv", ".360", ".lrv",
})


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def _natural(path: Path):
    """Sort key: '2 - x' before '10 - x', case-insensitive."""
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", str(path))]


def find_videos(paths, recursive: bool = True) -> list[Path]:
    """Video files among `paths`; folders are searched (with sub-folders if `recursive`).

    Files given directly are kept even with an unknown extension (the user chose them);
    files found in folders need a video extension. Hidden files / folders are skipped.
    Order: as given, each folder's content in natural order. No duplicates.
    """
    found: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            found.append(p)

    for p in map(Path, paths):
        if p.is_dir():
            pattern = p.rglob("*") if recursive else p.glob("*")
            inside = [f for f in pattern if f.is_file() and is_video(f)
                      and not any(part.startswith(".") for part in f.relative_to(p).parts)]
            for f in sorted(inside, key=_natural):
                add(f)
        elif p.is_file():
            add(p)
    return found


def clean_stem(path: Path) -> str:
    """File name without its video extensions: 'Clip.avi.MP4.AVI' → 'Clip' (renamed copies of
    old files often carry several). Never empty."""
    name = path.name
    while True:
        stem, dot, ext = name.rpartition(".")
        if not dot or not stem or f".{ext.lower()}" not in VIDEO_EXTENSIONS:
            break
        name = stem
    name = name.strip(" .")
    return name or path.stem


def quality_value(codec_key: str, level: int) -> int | None:
    """The codec's own quality number for level `level` (0 = best) – None = codec default."""
    codec = formats.CODECS_BY_KEY.get(codec_key)
    levels = formats.quality_levels(codec) if codec else []
    return levels[level][2] if 0 <= level < len(levels) else None


def make_job(info: MediaInfo, frames: FrameMap | None, codec_key: str, level: int = DEFAULT_LEVEL,
             sound: bool = True) -> Job:
    """Every frame once at the file's frame rate, source size, MP4 (speed None = lossless speed,
    so a phone slow-mo file keeps playing exactly as the file does)."""
    settings = OutputSettings(fps=info.fps, speed=None, codec=codec_key, container=CONTAINER,
                              quality=quality_value(codec_key, level), audio=sound)
    return Job(info, settings, frames=frames)


def output_folder(source: Path, folder: Path | None) -> Path:
    """`folder`, or the 'Converted' folder next to the source."""
    return folder if folder is not None else source.parent / FOLDER_NAME


def plan(jobs: list[tuple[Job, list[str] | None]], folder: Path | None,
         policy: str = batch.RENAME) -> list[batch.Item]:
    """Output file for every job: '<clean name>.mp4' in `folder` / the 'Converted' folder."""
    return batch.plan(jobs, None, "{name}", policy,
                      folders=[output_folder(j.info.path, folder) for j, _ in jobs],
                      names=[clean_stem(j.info.path) for j, _ in jobs])
