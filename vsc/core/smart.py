# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Smart re-encode: copy the clip, re-encode only the sections marked for it, join into one file.

How the parts fit together:
- Every part is written as MPEG-TS, which puts the decoder headers (VPS/SPS/PPS) in front of
  each keyframe. Joined (concat demuxer, stream copy) into MP4 with the `hev1` / `avc3` tag –
  the sample entries that allow headers to change inside the stream – or into MKV. The `hvc1`
  / `avc1` tag Apple requires allows only one set of headers, so these files do not play on
  Apple devices.
- A copied part must start at a *safe* keyframe: an IDR picture, or a CRA picture without
  RASL pictures after it (those reference the GOP before – open GOP). `join_points` reads the
  NAL unit types from the bitstream. Re-encoded parts are widened to safe keyframes; the extra
  frames are encoded at the speed they have anyway.
- Re-encoded parts use the source codec with the source size / chroma / bit depth, closed
  GOPs and headers repeated at every keyframe, and a constant frame rate of their own.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from . import command, ffmpeg_bin, segments as seg
from .formats import COPY
from .job import Job, Trim
from .probe import FrameMap, MediaInfo
from .runner import Progress, Result

# source codec → encoder codec key (catalogue) and the MP4 tag that allows in-band headers
SMART_CODECS = {"hevc": ("x265", "hev1"), "h264": ("x264", "avc3")}
CONTAINERS = ("mp4", "mkv")
DEFAULT_OUT_FPS = Fraction(30)
ENCODER_EXTRA = {
    "x265": ["-x265-params", "log-level=error:repeat-headers=1:open-gop=0"],
    "x264": ["-x264-params", "repeat-headers=1:open-gop=0"],
}
APPLE_WARNING = ("Smart re-encoded files change the decoder headers inside the stream "
                 "(MP4 tag hev1 / avc3). Apple devices (QuickTime, iPhone, iPad, Final Cut) "
                 "cannot play them – VLC, mpv, Windows, Android, Chrome and Firefox can. "
                 "For Apple, re-encode the whole clip instead.")


def unavailable_reason(info: MediaInfo) -> str | None:
    if info.codec not in SMART_CODECS:
        return (f"Smart re-encode needs H.264 or HEVC footage – this clip is {info.codec}. "
                "Its parts could not be joined.")
    return None


# --------------------------------------------------------------------------- safe join points

_START = re.compile(b"\x00\x00\x01")


def _access_units(path: Path, info: MediaInfo, chunk: int = 1 << 20):
    """(nal types of each picture) in decode order, read from the Annex-B bitstream."""
    hevc = info.codec == "hevc"
    bsf = "hevc_mp4toannexb" if hevc else "h264_mp4toannexb"
    proc = subprocess.Popen([ffmpeg_bin.ffmpeg(), "-v", "error", "-i", str(path),
                             "-map", f"0:{info.stream_index}", "-c:v", "copy", "-bsf:v", bsf,
                             "-f", "hevc" if hevc else "h264", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            **ffmpeg_bin.POPEN_FLAGS)
    tail = b""
    current: list[int] | None = None
    while True:
        block = proc.stdout.read(chunk)
        if not block:
            break
        data = tail + block
        # a start code needs 3 more bytes (NAL header + first slice bits) – the last 6 bytes
        # are kept for the next block, so nothing is read twice or cut off
        cut = max(0, len(data) - 6)
        for m in _START.finditer(data, 0, cut + 3):
            if m.start() >= cut:
                break
            pos = m.end()
            b0 = data[pos]
            if hevc:
                t = (b0 >> 1) & 0x3F
                if t < 32 and data[pos + 2] & 0x80:      # first slice of a picture
                    if current is not None:
                        yield current
                    current = [t]
                elif t < 32 and current is not None:
                    current.append(t)
            else:
                t = b0 & 0x1F
                if t in (1, 5) and data[pos + 1] & 0x80:  # first_mb_in_slice == 0
                    if current is not None:
                        yield current
                    current = [t]
        tail = data[cut:]
    if current is not None:
        yield current
    proc.wait()


def _decode_order_pts(path: Path, info: MediaInfo) -> list[int]:
    res = ffmpeg_bin.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams",
                          str(info.stream_index), "-show_entries", "packet=pts,dts",
                          "-of", "csv=p=0", str(path)], timeout=600)
    out = []
    for line in res.stdout.splitlines():
        parts = line.split(",")
        v = parts[0] if parts and parts[0] not in ("", "N/A") else (parts[1] if len(parts) > 1 else "")
        if v not in ("", "N/A"):
            out.append(int(v))
    return out


def join_points(path: Path, info: MediaInfo, frames: FrameMap) -> list[int]:
    """Display indices of keyframes where a copied part may start (see module docstring)."""
    if info.codec not in SMART_CODECS:
        return []
    hevc = info.codec == "hevc"
    pts = _decode_order_pts(path, info)
    aus = list(_access_units(path, info))
    if len(aus) != len(pts):           # unexpected stream layout – fall back to IDR-free none
        return [0] if frames.count else []
    index = {p: i for i, p in enumerate(frames.pts)}
    safe = []
    for i, types in enumerate(aus):
        if hevc:
            idr = any(t in (19, 20) for t in types)
            cra_ok = (any(t == 21 for t in types)
                      and not (i + 1 < len(aus) and any(t in (8, 9) for t in aus[i + 1])))
            ok = idr or cra_ok
        else:
            ok = 5 in types
        if ok and pts[i] in index:
            safe.append(index[pts[i]])
    return sorted(safe)


# --------------------------------------------------------------------------- plan

@dataclass(frozen=True)
class Part:
    kind: str                 # "copy" | "encode"
    start: int
    end: int                  # exclusive source frame
    fps: Fraction | None      # constant output rate of an encoded part
    frames: int               # output frames
    duration: Fraction        # seconds


def encode_ranges(job: Job, joins: list[int]) -> list[tuple[int, int, Fraction]]:
    """Source ranges to re-encode (widened to safe keyframes, merged) with their output fps."""
    start, end = job.trim.start, job.trim_end
    ranges = []
    for s in sorted(job.segments, key=lambda s: s.start):
        if not s.reencode or s.end <= start or s.start >= end:
            continue
        a, b = max(s.start, start), min(s.end, end)
        a = max([j for j in joins if j <= a] or [start])
        b = min([j for j in joins if j >= b] or [end])
        a, b = max(a, start), min(b, end)
        fps = Fraction(s.out_fps or DEFAULT_OUT_FPS)
        if ranges and a <= ranges[-1][1]:
            pa, pb, pf = ranges[-1]
            ranges[-1] = (pa, max(pb, b), pf)
        else:
            ranges.append((a, b, fps))
    return ranges


def plan(job: Job, joins: list[int]) -> list[Part]:
    start, end = job.trim.start, job.trim_end
    parts = []
    pos = start
    for a, b, fps in encode_ranges(job, joins) + [(end, end, None)]:
        if a > pos:
            ps = seg.pieces(job.segments, pos, a, job.info.real_fps)
            parts.append(Part("copy", pos, a, None, a - pos, seg.duration(ps)))
        if b > a:
            ps = seg.pieces(job.segments, a, b, job.info.real_fps)
            n = max(1, round(seg.duration(ps) * fps))
            parts.append(Part("encode", a, b, fps, n, Fraction(n) / fps))
        pos = max(pos, b)
    return parts


def part_job(job: Job, part: Part) -> Job:
    s = job.settings
    if part.kind == "copy":
        settings = replace(s, codec=COPY, smart=False, container="mkv")
    else:
        settings = replace(s, smart=False, fps=part.fps, speed=None, resize="source",
                           chroma=None, depth=None, container="mkv")
    return Job(job.info, settings, Trim(part.start, part.end), job.frames, job.segments)


# --------------------------------------------------------------------------- run

class SmartRunner:
    def __init__(self, job: Job, output: Path, joins: list[int] | None,
                 supported_pix_fmts: list[str] | None = None):
        if reason := unavailable_reason(job.info):
            raise command.CommandError(reason)
        if joins is None:
            raise command.CommandError("The keyframes of this clip are still being analysed")
        if job.trim.start not in joins and job.trim.start != 0:
            raise command.CommandError("The in-point must be on a keyframe where a part can start")
        self.job, self.output, self.joins = job, output, joins
        self.parts = plan(job, joins)
        self.supported = supported_pix_fmts
        self._proc: subprocess.Popen | None = None
        self._cancelled = False
        self._lock = threading.Lock()

    def _part_args(self, part: Part, out: Path) -> list[str]:
        pj = part_job(self.job, part)
        if part.kind == "copy":
            return command.copy_args(pj, out, timing="setts")
        codec_key = SMART_CODECS[self.job.info.codec][0]
        pj.settings.codec = codec_key
        _, _, pix = pj.output_format(self.supported)
        args = command.decode_args(pj, pix)
        args.insert(args.index("-i"), "-noautorotate")        # keep the coded orientation
        enc = command.encode_args(pj, out)
        flag = ENCODER_EXTRA[codec_key][0]
        if flag in enc:                                         # merge with the codec's params
            i = enc.index(flag)
            enc[i + 1] = enc[i + 1] + ":" + ENCODER_EXTRA[codec_key][1]
        else:
            enc[-1:-1] = ENCODER_EXTRA[codec_key]
        enc[-1:-1] = ["-g", str(max(1, pj.output_frame_count))]   # one closed GOP per part
        return args + enc

    def _join_args(self, listing: Path) -> list[str]:
        args = command._base_args() + ["-f", "concat", "-safe", "0"]
        if self.job.info.rotation:
            # MPEG-TS parts lose the display matrix – set it again (same convention as probe)
            args += ["-display_rotation:v", str(self.job.info.rotation)]
        args += ["-i", str(listing), "-map", "0:v", "-c", "copy"]
        if self.job.container == "mp4":
            args += ["-tag:v", SMART_CODECS[self.job.info.codec][1]]
        return args + [str(self.output)]

    @property
    def args(self) -> list[str]:
        return self._join_args(Path("<parts.txt>"))

    def describe(self) -> list[list[str]]:
        return [self._part_args(p, Path(f"<part{i}.ts>")) for i, p in enumerate(self.parts)] \
            + [self.args]

    def cancel(self) -> None:
        self._cancelled = True
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.kill()

    def _run(self, args: list[str], on_line=None) -> tuple[int, str]:
        with self._lock:
            if self._cancelled:
                return -1, ""
            self._proc = proc = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, errors="replace", **ffmpeg_bin.POPEN_FLAGS)
        err: deque[str] = deque(maxlen=30)
        t = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
        t.start()
        for line in proc.stdout:
            if on_line:
                on_line(line.strip())
        proc.wait()
        t.join(timeout=2)
        return proc.returncode, "".join(err).strip()

    def run(self, on_progress=None) -> Result:
        start = time.monotonic()
        total = sum(p.frames for p in self.parts)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="vsc-smart-"))
        done, error = 0, ""

        def report(frame):
            if on_progress:
                elapsed = time.monotonic() - start
                fps = frame / elapsed if elapsed > 0 else 0.0
                eta = (total - frame) / fps if fps > 0 else None
                on_progress(Progress(min(frame, total), total, fps, elapsed, eta))
        try:
            listing = []
            for i, part in enumerate(self.parts):
                out = work / f"part{i:03d}.ts"

                def on_line(line, base=done):
                    key, _, value = line.partition("=")
                    if key == "frame" and value.isdigit():
                        report(base + int(value))
                rc, err = self._run(self._part_args(part, out), on_line)
                if self._cancelled:
                    break
                if rc != 0:
                    error = f"Part {i + 1} ({part.kind} {part.start}–{part.end - 1}): {err}"
                    break
                done += part.frames
                report(done)
                listing.append(f"file '{out.as_posix()}'\nduration {float(part.duration):.9f}\n")
            if not error and not self._cancelled:
                (work / "parts.txt").write_text("".join(listing))
                rc, err = self._run(self._join_args(work / "parts.txt"))
                if rc != 0 and not self._cancelled:
                    error = "Joining the parts failed: " + err
        finally:
            shutil.rmtree(work, ignore_errors=True)
        ok = not error and not self._cancelled
        return Result(ok=ok, cancelled=self._cancelled, output=self.output,
                      elapsed=time.monotonic() - start, frames=done if not ok else total,
                      error=error)
