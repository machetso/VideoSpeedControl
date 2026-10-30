# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Stored previews (0.93): files with CRC, clean-up rules, partial proxy rebuild."""
from __future__ import annotations

import subprocess
from fractions import Fraction

from vsc.core import ffmpeg_bin, preview, preview_cache
from vsc.core.probe import FrameMap, probe, scan_frames


def test_blocks_frames_and_joins(tmp_path):
    cache = preview_cache.PreviewCache(tmp_path)
    head = (1, 100, 384, 216, 1, 30, 60, 6)
    entries = [(f, bytes([f % 256]) * (10 + f)) for f in range(30, 60)]
    cache.save_chunk("fp", head, 30, entries)
    assert cache.load_chunk("fp", head, 30) == entries
    assert cache.load_chunk("fp", (1, 100, 320, 180, 1, 30, 60, 6), 30) is None   # other size
    f = cache.dir("fp") / "chunk_30.bin"
    b = bytearray(f.read_bytes()); b[len(b) // 2] ^= 1; f.write_bytes(bytes(b))
    assert cache.load_chunk("fp", head, 30) is None                               # damaged
    fm = FrameMap([0, 512, 1024], Fraction(1, 12288), [0], [(0, 48, 100), (512, 148, 90), (1024, 238, 95)])
    cache.save_frames("fp", fm)
    back = cache.load_frames("fp")
    assert (back.pts, back.time_base, back.keyframes, back.packets) == (fm.pts, fm.time_base, fm.keyframes, fm.packets)
    cache.save_joins("fp", 3, [0])
    assert cache.load_joins("fp", 3) == [0] and cache.load_joins("fp", 4) is None


def test_cleanup_rules(tmp_path):
    cache = preview_cache.PreviewCache(tmp_path / "previews")
    for name in ("open", "cst", "old", "batch"):
        d = cache.dir(name)
        d.mkdir(parents=True)
        (d / "chunk_0.bin").write_bytes(b"x" * 1000)
    folder = tmp_path / "treatments"
    folder.mkdir()
    (folder / "a.cst").write_text('{"source": {"fingerprint": "cst"}}')
    elsewhere = tmp_path / "b.cst"
    elsewhere.write_text('{"source": {"fingerprint": "batch"}}')
    cache.remember_cst(elsewhere)
    assert cache.cst_fingerprints(folder) == {"cst", "batch"}
    assert cache.cleanup({"open"}, cache.cst_fingerprints(folder)) == 1          # "old" goes
    assert {d.name for d in cache.root.iterdir() if d.is_dir()} == {"open", "cst", "batch"}
    # over the cap: the clip in the list stays, the least recently used .cst one goes first
    import os
    os.utime(cache.dir("batch"), (1000, 1000))
    assert cache.cleanup({"open"}, {"cst", "batch"}, cap=2500) == 1
    assert {d.name for d in cache.root.iterdir() if d.is_dir()} == {"open", "cst"}


def _proxy(args) -> list[bytes]:
    out = subprocess.run(args, capture_output=True, check=True, **ffmpeg_bin.POPEN_FLAGS).stdout
    return preview.split_jpegs(bytearray(out))


def test_partial_rebuild_matches_the_full_proxy(h264_clip):
    """A chunk decoded alone from its keyframe gives the same pictures as the whole run."""
    info = probe(h264_clip)
    frames = scan_frames(h264_clip, info.stream_index)
    full = _proxy(preview.proxy_args(info, frames))
    assert len(full) == frames.count
    parts = preview_cache.chunks(frames)
    a, b = parts[len(parts) // 2]
    part = _proxy(preview.proxy_args(info, frames, a, b))
    assert len(part) == b - a
    assert part == full[a:b]
