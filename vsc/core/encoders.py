"""Detect which encoders the bundled FFmpeg offers and which hardware encoders really work.

Hardware encoders are listed by every FFmpeg build, but only work with a matching GPU and
driver; some even crash on unsuitable systems. Each one is therefore test-encoded in its own
process with a timeout. Results are cached per FFmpeg version.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import ffmpeg_bin
from .formats import CODECS, Codec


@dataclass
class EncoderStatus:
    available: bool
    pix_fmts: list[str]
    reason: str = ""


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "VideoSpeedControl"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ffmpeg_version() -> str:
    res = ffmpeg_bin.run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-version"], timeout=20)
    return res.stdout.splitlines()[0] if res.stdout else "unknown"


def vaapi_device() -> str | None:
    devices = sorted(glob.glob("/dev/dri/renderD*"))
    return devices[0] if devices else None


def _compiled_encoders() -> set[str]:
    res = ffmpeg_bin.run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-encoders"], timeout=20)
    names = set()
    for line in res.stdout.splitlines():
        m = re.match(r"\s*V\S{5}\s+(\S+)", line)
        if m:
            names.add(m.group(1))
    return names


def _pix_fmts(encoder: str) -> list[str]:
    res = ffmpeg_bin.run([ffmpeg_bin.ffmpeg(), "-hide_banner", "-h", f"encoder={encoder}"],
                         timeout=20)
    m = re.search(r"Supported pixel formats:\s*(.+)", res.stdout)
    return m.group(1).split() if m else []


def hw_input_args(codec: Codec) -> list[str]:
    """Global options a hardware encoder needs before the input."""
    if codec.hw == "vaapi":
        return ["-vaapi_device", vaapi_device() or "/dev/dri/renderD128"]
    return []


def hw_filter_suffix(codec: Codec, pix_fmt: str) -> list[str]:
    """Filters to append so frames reach the hardware encoder."""
    if codec.hw == "vaapi":
        return [f"format={pix_fmt}", "hwupload"]
    return []


def _test_hw(codec: Codec, pix_fmts: list[str]) -> EncoderStatus:
    if codec.hw == "amf" and sys.platform != "win32":
        return EncoderStatus(False, pix_fmts, "AMD AMF is only available on Windows")
    if codec.hw == "vaapi" and (sys.platform == "win32" or not vaapi_device()):
        return EncoderStatus(False, pix_fmts, "No VAAPI device (/dev/dri/renderD*)")
    pix = "nv12" if codec.hw in ("qsv", "vaapi") else "yuv420p"
    args = [ffmpeg_bin.ffmpeg(), "-hide_banner", "-v", "error", *hw_input_args(codec),
            "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25:d=0.2"]
    if codec.hw == "vaapi":
        args += ["-vf", ",".join(hw_filter_suffix(codec, pix))]
    else:
        args += ["-pix_fmt", pix]
    args += ["-frames:v", "3", "-c:v", codec.encoder, "-f", "null", "-"]
    try:
        res = ffmpeg_bin.run(args, timeout=20)
    except subprocess.TimeoutExpired:
        return EncoderStatus(False, pix_fmts, "Test encode timed out")
    if res.returncode == 0:
        return EncoderStatus(True, pix_fmts)
    lines = [re.sub(r"^(\[[^\]]+\]\s*)+", "", ln) for ln in res.stderr.strip().splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    reason = lines[0] if lines else f"ffmpeg exit code {res.returncode}"
    # negative = killed by a signal (POSIX); 0xC0000005 = access violation (Windows)
    if res.returncode < 0 or res.returncode == 0xC0000005:
        reason = "ffmpeg crashed during the test (driver / library mismatch)"
    return EncoderStatus(False, pix_fmts, reason[:200])


def detect(use_cache: bool = True) -> dict[str, EncoderStatus]:
    """Status for every codec of the catalogue, keyed by Codec.key."""
    version = ffmpeg_version()
    cache_file = config_dir() / "encoders.json"
    if use_cache and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text())
            if cached.get("version") == version:
                return {k: EncoderStatus(**v) for k, v in cached["codecs"].items()}
        except (ValueError, KeyError, TypeError):
            pass

    compiled = _compiled_encoders()
    encoders = {c.encoder for c in CODECS if c.encoder in compiled}
    with ThreadPoolExecutor(max_workers=8) as pool:
        fmts = dict(zip(encoders, pool.map(_pix_fmts, encoders)))

    result: dict[str, EncoderStatus] = {}
    hw_codecs = []
    for c in CODECS:
        if c.encoder not in compiled:
            result[c.key] = EncoderStatus(False, [], "Not included in this FFmpeg build")
        elif c.hw:
            hw_codecs.append(c)
        else:
            result[c.key] = EncoderStatus(True, fmts[c.encoder])
    with ThreadPoolExecutor(max_workers=4) as pool:
        for c, status in zip(hw_codecs, pool.map(lambda c: _test_hw(c, fmts[c.encoder]), hw_codecs)):
            result[c.key] = status

    try:
        cache_file.write_text(json.dumps({
            "version": version,
            "codecs": {k: vars(v) for k, v in result.items()},
        }, indent=1))
    except OSError:
        pass
    return result
