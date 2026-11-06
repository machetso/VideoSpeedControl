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
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from . import command, ffmpeg_bin, segments as seg
from .formats import COPY
from .job import Job, Trim
from .probe import FrameMap, MediaInfo
from .runner import Progress, Result
from ..i18n import N_, tr

# source codec → encoder codec key (catalogue) and the MP4 tag that allows in-band headers
SMART_CODECS = {"hevc": ("x265", "hev1"), "h264": ("x264", "avc3")}
CONTAINERS = ("mp4", "mkv")
DEFAULT_OUT_FPS = Fraction(30)
ENCODER_EXTRA = {
    "x265": ["-x265-params", "log-level=error:repeat-headers=1:open-gop=0"],
    "x264": ["-x264-params", "repeat-headers=1:open-gop=0"],
}
APPLE_WARNING = N_("Smart re-encoded files change the decoder headers inside the stream "
                 "(MP4 tag hev1 / avc3). Apple devices (QuickTime, iPhone, iPad, Final Cut) "
                 "cannot play them – VLC, mpv, Windows, Android, Chrome and Firefox can. "
                 "For Apple, re-encode the whole clip instead.")


def unavailable_reason(info: MediaInfo) -> str | None:
    if info.codec not in SMART_CODECS:
        return tr("Smart re-encode needs H.264 or HEVC footage – this clip is %s. "
                  "Its parts could not be joined.", info.codec)
    return None


# --------------------------------------------------------------------------- safe join points

_START = re.compile(b"\x00\x00\x01")


class AnalysisError(Exception):
    """The keyframe analysis for smart re-encode could not read the clip."""


def parse_access_units(blocks: Iterable[bytes], hevc: bool) -> Iterator[list[int]]:
    """NAL unit types of each picture in decode order, from an Annex-B byte stream.

    Pure function (no FFmpeg) – `blocks` may split the stream anywhere, even inside a start code.
    """
    tail = b""
    current: list[int] | None = None
    for block in blocks:
        if not block:
            continue
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
    # start codes in the last 6 bytes can only begin NAL units of ≤ 3 bytes – never a slice
    if current is not None:
        yield current


def _access_units(path: Path, info: MediaInfo, chunk: int = 1 << 20) -> Iterator[list[int]]:
    """NAL types of each picture in decode order, from FFmpeg's Annex-B output of the clip.

    Raises AnalysisError if FFmpeg fails – a truncated stream must not look like a clip with
    fewer safe keyframes. Stopping the iteration early kills FFmpeg.
    """
    hevc = info.codec == "hevc"
    bsf = "hevc_mp4toannexb" if hevc else "h264_mp4toannexb"
    proc = subprocess.Popen([ffmpeg_bin.ffmpeg(), "-v", "error", "-nostdin", "-i", str(path),
                             "-map", f"0:{info.stream_index}", "-c:v", "copy", "-bsf:v", bsf,
                             "-f", "hevc" if hevc else "h264", "-"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, **ffmpeg_bin.POPEN_FLAGS)
    err: deque[bytes] = deque(maxlen=30)
    reader = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
    reader.start()
    completed = False
    try:
        yield from parse_access_units(iter(lambda: proc.stdout.read(chunk), b""), hevc)
        completed = True
    finally:
        if not completed and proc.poll() is None:
            proc.kill()
        proc.wait()
        reader.join(timeout=2)
    if proc.returncode != 0:
        msg = b"".join(err).decode("utf-8", "replace").strip()
        raise AnalysisError(tr("Reading the bitstream failed (ffmpeg exit code %d)",
                               proc.returncode) + (f": {msg}" if msg else ""))


def _decode_order_pts(path: Path, info: MediaInfo) -> list[int]:
    res = ffmpeg_bin.run([ffmpeg_bin.ffprobe(), "-v", "error", "-select_streams",
                          str(info.stream_index), "-show_entries", "packet=pts,dts",
                          "-of", "csv=p=0", str(path)], timeout=600)
    if res.returncode != 0:
        raise AnalysisError(tr("Reading the packets failed (ffprobe exit code %d): %s",
                               res.returncode, res.stderr.strip()))
    out = []
    for line in res.stdout.splitlines():
        parts = line.split(",")
        v = parts[0] if parts and parts[0] not in ("", "N/A") else (parts[1] if len(parts) > 1 else "")
        if v not in ("", "N/A"):
            out.append(int(v))
    return out


def _packet_nal_types(f, pos: int, size: int, hevc: bool, length_size: int) -> list[int] | None:
    """VCL NAL types of one MP4 sample (length-prefixed NAL units), reading only their headers.

    None if the lengths do not add up to the sample size (other length size, not MP4 layout).
    """
    types, p = [], 0
    while p < size:
        f.seek(pos + p)
        head = f.read(length_size + 1)
        if len(head) < length_size + 1:
            return None
        n = int.from_bytes(head[:length_size], "big")
        if n == 0 or p + length_size + n > size:
            return None
        t = (head[length_size] >> 1) & 0x3F if hevc else head[length_size] & 0x1F
        if (hevc and t < 32) or (not hevc and t in (1, 5)):
            types.append(t)
        p += length_size + n
    return types


def _keyframe_types(path: Path, info: MediaInfo,
                    frames: FrameMap) -> dict[int, list[int]] | None:
    """NAL types of the keyframe packets and the packets right after them, by decode index.

    Reads a few header bytes per keyframe from the file (MP4 / MOV samples are length-prefixed
    NAL units at the positions `scan_frames` recorded) – no extra pass over the clip. None if
    that is not possible; the caller then reads the whole bitstream.
    """
    packets = frames.packets
    if not packets or not any(c in info.container.split(",") for c in ("mp4", "mov")):
        return None
    hevc = info.codec == "hevc"
    keys = set(frames.pts[k] for k in frames.keyframes)
    wanted = sorted({j for i, (pts, _, _) in enumerate(packets) if pts in keys
                     for j in (i, i + 1) if j < len(packets)})
    if any(packets[i][1] < 0 or packets[i][2] <= 0 for i in wanted):
        return None
    with open(path, "rb") as f:
        for length_size in (4, 2, 1):             # nearly always 4 (lengthSizeMinusOne = 3)
            out = {}
            for i in wanted:
                types = _packet_nal_types(f, packets[i][1], packets[i][2], hevc, length_size)
                if types is None:
                    break
                out[i] = types
            else:
                return out
    return None


def _safe(types: list[int], next_types: list[int] | None, hevc: bool) -> bool:
    """IDR, or a CRA not followed by RASL pictures (open GOP); H.264: IDR."""
    if not hevc:
        return 5 in types
    if any(t in (19, 20) for t in types):
        return True
    return 21 in types and not (next_types and any(t in (8, 9) for t in next_types))


def join_points(path: Path, info: MediaInfo, frames: FrameMap) -> list[int]:
    """Display indices of keyframes where a copied part may start (see module docstring).

    Fast path: only the keyframe packets are read (`_keyframe_types`). Otherwise – no packet
    positions, or not MP4 / MOV – the whole bitstream is read once. Raises AnalysisError if
    the clip cannot be read.
    """
    if info.codec not in SMART_CODECS:
        return []
    hevc = info.codec == "hevc"
    index = {p: i for i, p in enumerate(frames.pts)}
    by_packet = _keyframe_types(path, info, frames)
    if by_packet is not None:
        pts = [p for p, _, _ in frames.packets]
        keys = {frames.pts[k] for k in frames.keyframes}
        # by_packet also holds the packets after the keyframes (for the RASL check) – skip them
        return sorted(index[pts[i]] for i, types in by_packet.items()
                      if pts[i] in keys and _safe(types, by_packet.get(i + 1), hevc))
    # fallback: decode order from the scan if it has it, then every picture's NAL types
    pts = [p for p, _, _ in frames.packets] if frames.packets else _decode_order_pts(path, info)
    aus = list(_access_units(path, info))
    if len(aus) != len(pts):           # unexpected stream layout – only the very start is safe
        return [0] if frames.count else []
    return sorted(index[pts[i]] for i, types in enumerate(aus)
                  if pts[i] in index and _safe(types, aus[i + 1] if i + 1 < len(aus) else None, hevc))


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
    for s in sorted(job.timing_segments, key=lambda s: s.start):
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
    segments = job.timing_segments
    for a, b, fps in encode_ranges(job, joins) + [(end, end, None)]:
        if a > pos:
            ps = seg.pieces(segments, pos, a, job.info.real_fps)
            parts.append(Part("copy", pos, a, None, a - pos, seg.duration(ps)))
        if b > a:
            ps = seg.pieces(segments, a, b, job.info.real_fps)
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
    # the ramps are already laid in – without the smooth flags the part does not add them again
    segments = [replace(s, smooth_start=False, smooth_end=False) for s in job.timing_segments]
    return Job(job.info, settings, Trim(part.start, part.end), job.frames, segments)


# --------------------------------------------------------------------------- run

class SmartRunner:
    def __init__(self, job: Job, output: Path, joins: list[int] | None,
                 supported_pix_fmts: list[str] | None = None):
        if reason := unavailable_reason(job.info):
            raise command.CommandError(reason)
        if joins is None:
            raise command.CommandError(tr("The keyframes of this clip are still being analysed"))
        if job.trim.start not in joins and job.trim.start != 0:
            raise command.CommandError(tr("The in-point must be on a keyframe where a part can start"))
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
                    error = tr("Part %d (%s %d–%d): %s", i + 1, part.kind, part.start, part.end - 1, err)
                    break
                done += part.frames
                report(done)
                listing.append(f"file '{out.as_posix()}'\nduration {float(part.duration):.9f}\n")
            if not error and not self._cancelled:
                (work / "parts.txt").write_text("".join(listing))
                rc, err = self._run(self._join_args(work / "parts.txt"))
                if rc != 0 and not self._cancelled:
                    error = tr("Joining the parts failed: %s", err)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        ok = not error and not self._cancelled
        return Result(ok=ok, cancelled=self._cancelled, output=self.output,
                      elapsed=time.monotonic() - start, frames=done if not ok else total,
                      error=error)
