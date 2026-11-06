# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""AI frame interpolation with rife-ncnn-vulkan (Vulkan: NVIDIA, AMD, Intel incl. iGPUs).

Pipeline, piece by piece so temporary disk use stays bounded:
  ffmpeg: source frames → PNG  →  rife-ncnn-vulkan -n  →  PNG stream → one ffmpeg encoder.

Timing: with `-n n` on L input files rife places output i at position i·L/n (counting from
the first file, clamped at the last one). The rest of the app places output frame k at source
position k/ratio. Both agree when L·ratio is an integer, so every piece gets L = a multiple of
the ratio's denominator, which includes the following frame(s) the last outputs blend towards.
The ratio is rounded to a small denominator first; this changes the speed by at most
RATIO_TOLERANCE (0.05 %) – far below anything visible.

RIFE works on 8-bit RGB: 10-bit / HDR sources lose precision.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from . import command, ffmpeg_bin
from .encoders import hw_input_args
from .job import Job, Mode
from .runner import Progress, Result
from ..i18n import tr

MODELS = {"rife": "rife-v4.6", "rife_hq": "rife-v4.6"}
# High quality = temporal test-time augmentation (both directions): 2× the time. Spatial TTA
# (-x) was measured at 8× the time on an Intel UHD 620 for little visible gain – not used.
HQ_ARGS = {"rife_hq": ["-z"]}
UHD_WIDTH = 2560                         # rife's UHD mode (coarser flow) for frames this wide
RATIO_TOLERANCE = 5e-4
DISK_BUDGET = 2_000_000_000              # bytes of temporary PNGs per piece (inputs + outputs)
PNG_BYTES_PER_PIXEL = 2.0                # 8-bit RGB PNG of camera footage, roughly
EXE = "rife-ncnn-vulkan" + (".exe" if sys.platform == "win32" else "")

# colour matrix used for YUV ↔ RGB – the same in both directions, so colours survive exactly
MATRICES = {"bt709": "bt709", "smpte170m": "bt601", "bt470bg": "bt601", "bt2020nc": "bt2020",
            "fcc": "fcc", "smpte240m": "smpte240m"}


# --------------------------------------------------------------------------- binary / GPU

def find() -> Path | None:
    dirs = []
    if env := os.environ.get("VSC_RIFE_DIR"):
        dirs.append(Path(env))
    if hasattr(sys, "_MEIPASS"):
        dirs.append(Path(sys._MEIPASS) / "vendor" / "rife" / ffmpeg_bin.PLATFORM_DIR)
    dirs.append(Path(__file__).resolve().parents[2] / "vendor" / "rife" / ffmpeg_bin.PLATFORM_DIR)
    for d in dirs:
        if (d / EXE).is_file() and (d / MODELS["rife"]).is_dir():
            return d / EXE
    return None


@dataclass
class RifeStatus:
    available: bool
    gpu: str = ""            # name of the Vulkan device rife uses
    software: bool = False   # only a CPU (llvmpipe / SwiftShader) Vulkan device – very slow
    reason: str = ""


_status: RifeStatus | None = None


def detect(refresh: bool = False) -> RifeStatus:
    """Run rife once on two tiny frames; cached for the session."""
    global _status
    if _status and not refresh:
        return _status
    exe = find()
    if exe is None:
        _status = RifeStatus(False, reason=tr("%s not installed (%s)", "rife-ncnn-vulkan",
                                              "python tools/fetch_rife.py"))
        return _status
    with tempfile.TemporaryDirectory(prefix="vsc-rife-") as tmp:
        tmp = Path(tmp)
        for i, c in enumerate(("black", "white")):
            ffmpeg_bin.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-f", "lavfi", "-i",
                            f"color=c={c}:s=64x64", "-frames:v", "1", str(tmp / f"{i}.png")])
        try:
            res = subprocess.run([str(exe), "-0", str(tmp / "0.png"), "-1", str(tmp / "1.png"),
                                  "-o", str(tmp / "out.png"), "-m", MODELS["rife"]],
                                 cwd=exe.parent, capture_output=True, text=True,
                                 errors="replace", timeout=60, **ffmpeg_bin.POPEN_FLAGS)
        except subprocess.TimeoutExpired:
            _status = RifeStatus(False, reason=tr("RIFE test timed out"))
            return _status
        gpus = re.findall(r"^\[0 ([^\]]+)\]", res.stderr, re.M)
        gpu = gpus[0] if gpus else ""
        if res.returncode != 0 or not (tmp / "out.png").is_file():
            lines = [ln for ln in res.stderr.splitlines() if ln.strip()]
            reason = lines[-1][:200] if lines else tr("RIFE failed (no Vulkan device?)")
            _status = RifeStatus(False, gpu, reason=reason)
        else:
            soft = bool(re.search(r"llvmpipe|swiftshader|lavapipe", gpu, re.I))
            _status = RifeStatus(True, gpu, soft)
    return _status


# --------------------------------------------------------------------------- planning

def grid_ratio(job: Job) -> Fraction:
    """Output frames per source frame, rounded to the smallest denominator within tolerance."""
    exact = Fraction(job.settings.fps) / (job.speed * job.info.real_fps)
    for q in range(1, 1001):
        r = Fraction(round(exact * q), q)
        if r > 0 and abs(float(r / exact) - 1) <= RATIO_TOLERANCE:
            return r
    return exact.limit_denominator(1000)


@dataclass
class Piece:
    start: int       # first source frame
    files: int       # source frames handed to rife (beyond the clip end: last frame repeated)
    n: int           # frames rife computes (files · ratio)
    keep: int        # of those, the first `keep` are used


def piece_frames(job: Job, ratio: Fraction) -> int:
    """Source frames per piece (a multiple of the ratio's denominator) within DISK_BUDGET."""
    w, h = rife_size(job)
    per_src = w * h * PNG_BYTES_PER_PIXEL * (1 + float(ratio))
    q = ratio.denominator
    return max(q, int(DISK_BUDGET / per_src) // q * q)


def plan(job: Job, ratio: Fraction, src_per_piece: int | None = None) -> list[Piece]:
    q = ratio.denominator
    src_per_piece = src_per_piece or piece_frames(job, ratio)
    total_out = job.output_frame_count
    per_piece = int(src_per_piece * ratio)
    pieces, k, start = [], 0, job.trim.start
    while k < total_out:
        keep = min(per_piece, total_out - k)
        # the last kept output blends towards source frame floor(pos) + 1
        need = math.floor(Fraction(keep - 1) / ratio) + 2
        files = q * math.ceil(need / q)
        pieces.append(Piece(start, files, int(files * ratio), keep))
        k += keep
        start += src_per_piece
    return pieces


def rife_size(job: Job) -> tuple[int, int]:
    """Frame size rife works on: the output size if that is smaller (faster), else the source."""
    return job.output_size() if command.shrinks(job) else job.info.display_size


def _matrix(job: Job) -> tuple[str, str]:
    i = job.info
    return MATRICES.get(i.color_space or "", "bt601"), "pc" if i.color_range == "pc" else "tv"


# --------------------------------------------------------------------------- running

class RifeRunner:
    """Same interface as runner.Runner. `cancel()` may be called from another thread."""

    def __init__(self, job: Job, output: Path, supported_pix_fmts: list[str] | None = None):
        if find() is None:
            raise command.CommandError(tr("RIFE is not installed (%s)", "python tools/fetch_rife.py"))
        self.job = job
        self.output = output
        self.ratio = grid_ratio(job)
        self.pieces = plan(job, self.ratio)
        self.exe = find()
        _, _, self.pix_fmt = job.output_format(supported_pix_fmts)
        self.encoder_args = self._encoder_args()
        self._procs: list[subprocess.Popen] = []
        self._cancelled = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ commands

    def _extract_args(self, piece: Piece, folder: Path) -> list[str]:
        job = self.job
        matrix, rng = _matrix(job)
        chain = [f"trim=end_frame={piece.files}"]
        if command.shrinks(job):
            chain += command.scale_filters(job)
        chain.append(f"scale=in_color_matrix={matrix}:in_range={rng}")
        chain.append("format=rgb24")
        args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-nostdin"]
        if piece.start:
            args += ["-ss", command._num(command.seek_time(job, piece.start))]
        args += ["-i", str(job.info.path), "-map", f"0:{job.info.stream_index}",
                 "-an", "-sn", "-dn", "-vf", ",".join(chain), "-frames:v", str(piece.files),
                 "-compression_level", "1", "-start_number", "1", str(folder / "%08d.png")]
        return args

    def _rife_args(self, piece: Piece, src: Path, dst: Path) -> list[str]:
        method = self.job.settings.interpolation
        return [str(self.exe), "-i", str(src), "-o", str(dst), "-n", str(piece.n),
                "-m", MODELS[method], "-v", *HQ_ARGS.get(method, []),
                *(["-u"] if rife_size(self.job)[0] >= UHD_WIDTH else [])]

    def _encoder_args(self) -> list[str]:
        job = self.job
        matrix, rng = _matrix(job)
        chain = [] if command.shrinks(job) else command.scale_filters(job)
        chain.append(f"scale=out_color_matrix={matrix}:out_range={rng}")
        chain += command.pixel_filters(job, self.pix_fmt)
        return (command._base_args() + hw_input_args(job.codec)
                + ["-f", "image2pipe", "-framerate", str(job.settings.fps), "-c:v", "png",
                   "-i", "-", "-vf", ",".join(chain),
                   "-frames:v", str(job.output_frame_count)]
                + command.encode_args(job, self.output))

    @property
    def args(self) -> list[str]:
        """For display: the encoder command (piece commands are similar for every piece)."""
        return self.encoder_args

    def describe(self) -> list[list[str]]:
        folder = Path("<tmp>")
        p = self.pieces[0]
        return [self._extract_args(p, folder / "in"),
                self._rife_args(p, folder / "in", folder / "out"), self.encoder_args]

    # ------------------------------------------------------------------ run

    def cancel(self) -> None:
        self._cancelled = True
        with self._lock:
            for proc in self._procs:
                if proc.poll() is None:
                    proc.kill()

    def _popen(self, args, **kw) -> subprocess.Popen:
        with self._lock:
            if self._cancelled:
                raise _Cancelled
            proc = subprocess.Popen(args, **kw, **ffmpeg_bin.POPEN_FLAGS)
            self._procs.append(proc)
            return proc

    def run(self, on_progress=None) -> Result:
        start = time.monotonic()
        total = self.job.output_frame_count
        self.output.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="vsc-rife-"))
        enc_err: deque[str] = deque(maxlen=40)
        done = 0
        error = ""
        enc = None
        try:
            enc = self._popen(self.encoder_args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE)
            threading.Thread(target=lambda: enc_err.extend(
                ln.decode("utf-8", "replace") for ln in enc.stderr), daemon=True).start()

            def report(frame):
                if on_progress:
                    elapsed = time.monotonic() - start
                    fps = frame / elapsed if elapsed > 0 else 0.0
                    eta = (total - frame) / fps if fps > 0 else None
                    on_progress(Progress(frame, total, fps, elapsed, eta))

            for piece in self.pieces:
                src, dst = work / "in", work / "out"
                for d in (src, dst):
                    shutil.rmtree(d, ignore_errors=True)
                    d.mkdir()
                ext = self._popen(self._extract_args(piece, src), stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE)
                _, err = ext.communicate()
                if ext.returncode != 0:
                    raise _Failed(tr("Extracting frames failed: %s", err.decode("utf-8", "replace")))
                files = sorted(src.glob("*.png"))
                if not files:
                    raise _Failed(tr("No frames extracted"))
                for i in range(len(files) + 1, piece.files + 1):   # past the clip end
                    shutil.copyfile(files[-1], src / f"{i:08d}.png")

                rife = self._popen(self._rife_args(piece, src, dst), cwd=self.exe.parent,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                   text=True, errors="replace")
                rife_err: deque[str] = deque(maxlen=20)
                computed = 0
                for line in rife.stderr:
                    rife_err.append(line)
                    if line.rstrip().endswith("done"):
                        computed += 1
                        report(done + min(computed, piece.keep) * 0.9)
                rife.wait()
                if rife.returncode != 0:
                    raise _Failed(tr("RIFE failed: %s", "".join(rife_err)[-800:]))

                for i in range(1, piece.keep + 1):
                    enc.stdin.write((dst / f"{i:08d}.png").read_bytes())
                done += piece.keep
                report(done)
            enc.stdin.close()
            enc.wait()
            if enc.returncode != 0 and not self._cancelled:
                raise _Failed("".join(enc_err))
        except _Cancelled:
            pass
        except _Failed as e:
            error = str(e).strip()
        except (BrokenPipeError, OSError) as e:
            error = ("".join(enc_err) or str(e)).strip()
        finally:
            if enc and enc.poll() is None:
                enc.kill()
            shutil.rmtree(work, ignore_errors=True)
        ok = not error and not self._cancelled
        return Result(ok=ok, cancelled=self._cancelled, output=self.output,
                      elapsed=time.monotonic() - start, frames=done,
                      error=error)


class _Cancelled(Exception):
    pass


class _Failed(Exception):
    pass


def is_rife(job: Job) -> bool:
    return (job.mode == Mode.INTERPOLATE and job.settings.interpolation in MODELS
            and not job.has_segments)
