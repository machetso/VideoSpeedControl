"""AV2 with the AVM reference software (avmenc / avmdec) – FFmpeg cannot encode or decode AV2.

Pipeline: ffmpeg decodes, trims, retimes and scales exactly as for any other codec and pipes
y4m into avmenc, which writes IVF or WebM. For the test-encode comparison avmdec decodes the
result back into a lossless FFV1 file that the rest of the app (ffmpeg) can read.

The reference encoder is a research tool: minutes per 1080p frame (see CLAUDE.md).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

from . import command, ffmpeg_bin
from .encoders import EncoderStatus
from .job import Job
from .runner import Progress, Result

VERSION = "v1.0.0"
EXT = ".exe" if sys.platform == "win32" else ""
PIX_FMTS = ["yuv420p", "yuv422p", "yuv444p", "yuv420p10le", "yuv422p10le", "yuv444p10le"]
THREADS = max(1, min(os.cpu_count() or 4, 16))

# ffmpeg colour names → AVM's CICP names (unknown ones are left out = unspecified)
PRIMARIES = {"bt709": "bt709", "smpte170m": "bt601", "bt470bg": "bt470bg", "bt470m": "bt470m",
             "smpte240m": "smpte240", "film": "film", "bt2020": "bt2020"}
TRANSFER = {"bt709": "bt709", "smpte170m": "bt601", "bt470bg": "bt470bg", "gamma22": "bt470m",
            "smpte240m": "smpte240", "linear": "lin", "iec61966-2-1": "srgb",
            "iec61966-2-4": "iec61966", "bt2020-10": "bt2020-10bit", "bt2020-12": "bt2020-12bit",
            "smpte2084": "smpte2084", "arib-std-b67": "hlg"}
MATRIX = {"bt709": "bt709", "smpte170m": "bt601", "bt470bg": "bt470bg", "fcc": "fcc73",
          "smpte240m": "smpte240", "bt2020nc": "bt2020ncl", "bt2020c": "bt2020cl"}


def find(name: str = "avmenc") -> Path | None:
    dirs = []
    if env := os.environ.get("VSC_AVM_DIR"):
        dirs.append(Path(env))
    if hasattr(sys, "_MEIPASS"):
        dirs.append(Path(sys._MEIPASS) / "vendor" / "avm" / ffmpeg_bin.PLATFORM_DIR)
    dirs.append(Path(__file__).resolve().parents[2] / "vendor" / "avm" / ffmpeg_bin.PLATFORM_DIR)
    for d in dirs:
        exe = d / (name + EXT)
        if exe.is_file():
            return exe
    return None


def detect() -> EncoderStatus:
    exe = find()
    if not exe or not find("avmdec"):
        return EncoderStatus(False, [], "AVM (AV2 reference encoder) is not installed – "
                                        "run tools/fetch_avm.py")
    try:
        res = subprocess.run([str(exe), "--help"], capture_output=True, timeout=20,
                             **ffmpeg_bin.POPEN_FLAGS)
    except (OSError, subprocess.TimeoutExpired) as e:
        return EncoderStatus(False, [], f"avmenc does not start: {e}")
    if b"--cpu-used" not in res.stdout + res.stderr:
        return EncoderStatus(False, [], "avmenc does not start")
    return EncoderStatus(True, list(PIX_FMTS))


def encoder_args(job: Job, output: Path) -> list[str]:
    """avmenc reading y4m from stdin."""
    codec, s, info = job.codec, job.settings, job.info
    args = [str(find()), "--threads=%d" % THREADS, "--row-mt=1", "--tile-columns=2",
            "--passes=1", "-q"]
    preset = s.preset if s.preset in codec.presets else codec.default_preset
    args.append(f"{codec.preset_flag}={preset}")
    if codec.quality:
        q = s.quality if s.quality is not None else codec.quality.default
        q = min(max(q, codec.quality.minimum), codec.quality.maximum)
        args += [a.replace("{q}", str(q)) for a in codec.quality.args]
    args += list(codec.args)
    for value, table, flag in ((info.color_primaries, PRIMARIES, "color-primaries"),
                               (info.color_transfer, TRANSFER, "transfer-characteristics"),
                               (info.color_space, MATRIX, "matrix-coefficients")):
        if value in table:
            args.append(f"--{flag}={table[value]}")
    fps = Fraction(s.fps)
    args.append(f"--fps={fps.numerator}/{fps.denominator}")
    args.append("--webm" if job.container == "webm" else "--ivf")
    return args + ["-o", str(output), "-"]


class AvmRunner:
    """ffmpeg (decode, retime, scale → y4m) | avmenc. `cancel()` may be called from any thread."""

    def __init__(self, job: Job, output: Path, supported_pix_fmts: list[str] | None = None):
        if not find():
            raise command.CommandError(detect().reason)
        self.job, self.output = job, output
        _, _, pix_fmt = job.output_format(PIX_FMTS)
        self.ffmpeg_args = (command.decode_args(job, pix_fmt)
                            + ["-f", "yuv4mpegpipe", "-strict", "-1", "-"])
        self.encoder_args = encoder_args(job, output)
        self._procs: list[subprocess.Popen] = []
        self._cancelled = False

    @property
    def args(self) -> list[str]:
        return self.encoder_args

    def describe(self) -> list[list[str]]:
        return [self.ffmpeg_args, self.encoder_args]

    def cancel(self) -> None:
        self._cancelled = True
        for proc in self._procs:
            if proc.poll() is None:
                proc.kill()

    def run(self, on_progress=None) -> Result:
        total = self.job.output_frame_count
        self.output.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        enc = subprocess.Popen(self.encoder_args, stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               **ffmpeg_bin.POPEN_FLAGS)
        # frames: ffmpeg stdout → avmenc stdin; progress lines: ffmpeg stderr (portable)
        args = ["pipe:2" if a == "pipe:1" else a for a in self.ffmpeg_args]
        dec = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=enc.stdin,
                               stderr=subprocess.PIPE, **ffmpeg_bin.POPEN_FLAGS)
        enc.stdin.close()          # the encoder sees EOF when ffmpeg is done
        self._procs = [dec, enc]
        if self._cancelled:
            self.cancel()
        errors: deque[str] = deque(maxlen=40)
        enc_thread = threading.Thread(target=lambda: errors.extend(
            ln.decode("utf-8", "replace") for ln in enc.stderr), daemon=True)
        enc_thread.start()

        frame = 0
        for raw in dec.stderr:
            line = raw.decode("utf-8", "replace").strip()
            key, sep, value = line.partition("=")
            if not sep or " " in key:
                errors.append(line + "\n")
            elif key == "frame" and value.isdigit():
                frame = int(value)
            elif key == "progress" and on_progress:
                # frames handed to the encoder; it lags a few frames behind
                elapsed = time.monotonic() - start
                fps = frame / elapsed if elapsed > 0 else 0.0
                eta = (total - frame) / fps if fps > 0 else None
                on_progress(Progress(min(frame, total), total, fps, elapsed, eta))
        dec.wait()
        enc.wait()
        enc_thread.join(timeout=2)
        ok = dec.returncode == 0 and enc.returncode == 0 and not self._cancelled
        error = "" if ok or self._cancelled else "".join(errors).strip() or "AV2 encoding failed"
        return Result(ok=ok, cancelled=self._cancelled, output=self.output,
                      elapsed=time.monotonic() - start, frames=total if ok else frame,
                      error=error)


def decode_for_preview(src: Path, dst: Path, timeout: float = 600) -> None:
    """AV2 file → lossless FFV1 MKV that ffmpeg can read (for the comparison view)."""
    dec = subprocess.Popen([str(find("avmdec")), "-o", "-", str(src)], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, **ffmpeg_bin.POPEN_FLAGS)
    res = subprocess.run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", "-y",
                          "-f", "yuv4mpegpipe", "-i", "-", "-c:v", "ffv1", str(dst)],
                         stdin=dec.stdout, capture_output=True, timeout=timeout,
                         **ffmpeg_bin.POPEN_FLAGS)
    dec.stdout.close()
    dec.wait(timeout=timeout)
    if dec.returncode != 0 or res.returncode != 0:
        msg = (dec.stderr.read().decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace"))
        raise ValueError(f"Cannot decode the AV2 file: {msg.strip()[:300]}")
