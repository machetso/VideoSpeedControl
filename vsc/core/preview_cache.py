# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Stored previews (user, 0.93 – the same idea and file format as the Android app).

A video opened again does not rebuild its frame list (packet scan), its smart keyframe
analysis, its timeline thumbnails and its scrubbing proxy: they are kept per video in the cache
folder, named by the .cst fingerprint (a renamed / moved file still matches, a changed file does
not). The proxy is stored in chunks from keyframe to keyframe, each with a CRC32: a damaged or
missing chunk is rebuilt alone, and chunks are written while the proxy is built.

Clean-up rule: a preview stays while its video is in the clip list, in the batch list or has a
.cst file (in the treatments folder or saved anywhere else by this app); the others are deleted.
Above 2 GB the least recently used go first – those without a .cst before those with one.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import time
import zlib
from fractions import Fraction
from pathlib import Path

from .probe import FrameMap

VERSION = 1
CAP_BYTES = 2 * 1024 ** 3
MAGIC = b"VSCP"
TREATMENTS_FOLDER = ("VideoSpeedControl", "Clip Speed Treatments")


def cache_root() -> Path:
    """Linux ~/.cache/VideoSpeedControl/previews, Windows %LOCALAPPDATA%\\VideoSpeedControl\\previews."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "VideoSpeedControl" / "previews"


def chunks(frames: FrameMap) -> list[tuple[int, int]]:
    """Frame ranges [start, end) from one keyframe to the next."""
    starts = sorted({0, *(k for k in frames.keyframes if 0 < k < frames.count)})
    return [(a, starts[i + 1] if i + 1 < len(starts) else frames.count) for i, a in enumerate(starts)]


class PreviewCache:
    def __init__(self, root: Path | None = None):
        self.root = root or cache_root()

    def dir(self, fingerprint: str) -> Path:
        return self.root / fingerprint

    def touch(self, fingerprint: str) -> None:
        d = self.dir(fingerprint)
        if d.is_dir():
            os.utime(d)

    # ------------------------------------------------------------------ frame list, keyframe analysis

    def load_frames(self, fingerprint: str) -> FrameMap | None:
        try:
            o = json.loads((self.dir(fingerprint) / "frames.json").read_text())
            if o["version"] != VERSION:
                return None
            packets = [tuple(p) for p in o["packets"]] if o.get("packets") is not None else None
            return FrameMap(o["pts"], Fraction(o["time_base"]), o["keyframes"], packets)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save_frames(self, fingerprint: str, frames: FrameMap) -> None:
        o = {"version": VERSION, "pts": frames.pts, "time_base": str(frames.time_base),
             "keyframes": frames.keyframes,
             "packets": [list(p) for p in frames.packets] if frames.packets is not None else None}
        _atomic_write(self._mkdir(fingerprint) / "frames.json", json.dumps(o).encode())

    def load_joins(self, fingerprint: str, count: int) -> list[int] | None:
        try:
            o = json.loads((self.dir(fingerprint) / "joins.json").read_text())
            return list(o["joins"]) if o["version"] == VERSION and o["frames"] == count else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save_joins(self, fingerprint: str, count: int, joins: list[int]) -> None:
        _atomic_write(self._mkdir(fingerprint) / "joins.json",
                      json.dumps({"version": VERSION, "frames": count, "joins": joins}).encode())

    # ------------------------------------------------------------------ thumbnails, proxy chunks

    def load_thumbs(self, fingerprint: str, count: int) -> list[tuple[int, bytes]] | None:
        """[(frame index, image bytes)] in slot order, or None."""
        return _read_block(self.dir(fingerprint) / "thumbs.bin", (VERSION, count))

    def save_thumbs(self, fingerprint: str, count: int, thumbs: list[tuple[int, bytes]]) -> None:
        _write_block(self._mkdir(fingerprint) / "thumbs.bin", (VERSION, count), thumbs)

    def load_chunk(self, fingerprint: str, header: tuple, start: int) -> list[tuple[int, bytes]] | None:
        return _read_block(self.dir(fingerprint) / f"chunk_{start}.bin", header)

    def save_chunk(self, fingerprint: str, header: tuple, start: int,
                   entries: list[tuple[int, bytes]]) -> None:
        _write_block(self._mkdir(fingerprint) / f"chunk_{start}.bin", header, entries)

    def _mkdir(self, fingerprint: str) -> Path:
        d = self.dir(fingerprint)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ .cst files

    def remember_cst(self, path: Path) -> None:
        """A .cst saved outside the treatments folder: its preview is kept while it exists."""
        index = self.root / "cst_files.json"
        paths = set(self._cst_paths())
        paths.add(str(path.resolve()))
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(index, json.dumps(sorted(paths)).encode())

    def _cst_paths(self) -> list[str]:
        try:
            return list(json.loads((self.root / "cst_files.json").read_text()))
        except (OSError, ValueError):
            return []

    def cst_fingerprints(self, folder: Path | None) -> set[str]:
        """Fingerprints of the videos that have a .cst: in `folder` or saved elsewhere."""
        files = [Path(p) for p in self._cst_paths()]
        if folder and folder.is_dir():
            files += folder.glob("*.cst")
        out = set()
        for f in files:
            try:
                out.add(json.loads(f.read_text(encoding="utf-8"))["source"]["fingerprint"])
            except (OSError, ValueError, KeyError, TypeError):
                pass
        return out

    # ------------------------------------------------------------------ clean-up

    def cleanup(self, in_use: set[str], with_cst: set[str], cap: int = CAP_BYTES) -> int:
        """Delete previews nobody needs (rule in the module doc); returns how many."""
        if not self.root.is_dir():
            return 0
        deleted, kept = 0, []
        for d in self.root.iterdir():
            if not d.is_dir():
                continue
            if d.name in in_use or d.name in with_cst:
                kept.append(d)
            else:
                shutil.rmtree(d, ignore_errors=True)
                deleted += 1
        total = sum(_size(d) for d in kept)
        for d in sorted((d for d in kept if d.name not in in_use),
                        key=lambda d: (d.name in with_cst, d.stat().st_mtime)):
            if total <= cap:
                break
            total -= _size(d)
            shutil.rmtree(d, ignore_errors=True)
            deleted += 1
        return deleted

    def total_bytes(self) -> int:
        return _size(self.root) if self.root.exists() else 0


def treatments_folder(documents: Path) -> Path:
    """Documents/VideoSpeedControl/Clip Speed Treatments (the default place for .cst files)."""
    return documents.joinpath(*TREATMENTS_FOLDER)


# --------------------------------------------------------------------------- file format

def _write_block(path: Path, header: tuple, entries: list[tuple[int, bytes]]) -> None:
    """"VSCP", header ints, entry count, entries (frame, length, bytes), CRC32 – like Android."""
    parts = [MAGIC, struct.pack(">i", len(header)), struct.pack(f">{len(header)}i", *header),
             struct.pack(">i", len(entries))]
    for frame, data in entries:
        parts += [struct.pack(">ii", frame, len(data)), data]
    body = b"".join(parts)
    _atomic_write(path, body + struct.pack(">q", zlib.crc32(body)))


def _read_block(path: Path, header: tuple) -> list[tuple[int, bytes]] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 16:
        return None
    body = data[:-8]
    if struct.unpack(">q", data[-8:])[0] != zlib.crc32(body) or not body.startswith(MAGIC):
        return None
    try:
        pos = 4
        (n,) = struct.unpack_from(">i", body, pos); pos += 4
        if tuple(struct.unpack_from(f">{n}i", body, pos)) != tuple(header):
            return None
        pos += 4 * n
        (count,) = struct.unpack_from(">i", body, pos); pos += 4
        out = []
        for _ in range(count):
            frame, size = struct.unpack_from(">ii", body, pos); pos += 8
            out.append((frame, body[pos:pos + size])); pos += size
        return out if pos == len(body) else None
    except struct.error:
        return None


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
