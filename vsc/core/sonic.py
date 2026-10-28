# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Sonic time stretching through ctypes – the same algorithm as the Android app.

native/sonic_media3/sonic_media3.c is a C port of Media3's Sonic (Apache-2.0), bit-exact with
the Java original (tests/test_sonic.py), so both apps sound the same. The user chose Sonic after
listening to rubberband, Rubber Band R3 and Signalsmith Stretch. Not the original C Sonic
(waywardgeek): its slow-down drifts (+30 ms per click at 8×, output too long) and its pitch
search often settles on a multiple of the period. Built by tools/build_sonic.py into
vendor/sonic/<platform>-x64/.
"""
from __future__ import annotations

import ctypes
import os
import sys
from functools import cache
from pathlib import Path

from .ffmpeg_bin import IS_WINDOWS, PLATFORM_DIR

LIB_NAME = "sonic.dll" if IS_WINDOWS else "libsonic.so"


def _candidate_dirs() -> list[Path]:
    dirs = []
    if env := os.environ.get("VSC_SONIC_DIR"):
        dirs.append(Path(env))
    if hasattr(sys, "_MEIPASS"):  # PyInstaller bundle
        dirs.append(Path(sys._MEIPASS) / "vendor" / "sonic" / PLATFORM_DIR)
    dirs.append(Path(__file__).resolve().parents[2] / "vendor" / "sonic" / PLATFORM_DIR)
    return dirs


@cache
def _lib() -> ctypes.CDLL | None:
    for d in _candidate_dirs():
        p = d / LIB_NAME
        if p.is_file():
            lib = ctypes.CDLL(str(p))
            vp, i, f = ctypes.c_void_p, ctypes.c_int, ctypes.c_float
            short_p = ctypes.POINTER(ctypes.c_short)
            for name, args, res in (
                ("m3s_create", [i, i, f, f, i], vp),
                ("m3s_destroy", [vp], None),
                ("m3s_queue_input", [vp, short_p, i], None),
                ("m3s_output_frames", [vp], i),
                ("m3s_read_output", [vp, short_p, i], i),
                ("m3s_queue_end_of_stream", [vp], None),
            ):
                fn = getattr(lib, name)
                fn.argtypes, fn.restype = args, res
            return lib
    return None


def unavailable_reason() -> str | None:
    if _lib() is None:
        return "The Sonic library is missing – run 'python tools/build_sonic.py'."
    return None


class Stream:
    """One Sonic stream (Media3 semantics): interleaved signed 16-bit PCM in, stretched PCM out.

    `speed` < 1 slows down (0.125 = 8× slower), the pitch stays; `out_rate` ≠ `rate` resamples.
    """

    def __init__(self, rate: int, channels: int, speed: float, out_rate: int | None = None):
        lib = _lib()
        if lib is None:
            raise RuntimeError(unavailable_reason())
        self._lib, self.channels = lib, channels
        self._h = lib.m3s_create(rate, channels, speed, 1.0, out_rate or rate)
        if not self._h:
            raise MemoryError("m3s_create failed")

    def write(self, pcm: bytes) -> None:
        frames = len(pcm) // (2 * self.channels)
        if frames:
            n = frames * self.channels
            buf = (ctypes.c_short * n).from_buffer_copy(pcm[:n * 2])
            self._lib.m3s_queue_input(self._h, buf, frames)

    def read(self) -> bytes:
        n = self._lib.m3s_output_frames(self._h)
        if n <= 0:
            return b""
        buf = (ctypes.c_short * (n * self.channels))()
        got = self._lib.m3s_read_output(self._h, buf, n)
        return bytes(buf)[:got * 2 * self.channels]

    def flush(self) -> bytes:
        """End of input (Media3 queueEndOfStream); returns the remaining output."""
        self._lib.m3s_queue_end_of_stream(self._h)
        return self.read()

    def close(self) -> None:
        if self._h:
            self._lib.m3s_destroy(self._h)
            self._h = None

    def __enter__(self) -> "Stream":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


@cache
def lead(rate: int, tempo: float, context: float) -> float:
    """How far Sonic moves the content early, in seconds of input (tempo = output / input speed).

    A click `context` seconds into a short signal goes through a stream set up exactly like the
    real one; the onset (first sample above half the peak) gives the lead – what the ear times in
    a smeared click. ~4–5 ms of input on the Android port (32 ms at 8× slower, 190 ms at 40×).
    """
    import array
    frames = int((context + 0.2) * rate)
    at = int(context * rate)
    width = max(1, rate // 2000)
    pcm = array.array("h", [0]) * (frames * 2)
    for i in range(at, at + width):
        pcm[2 * i] = pcm[2 * i + 1] = 29000
    with Stream(rate, 2, tempo) as s:
        s.write(pcm.tobytes())
        out = array.array("h", s.read() + s.flush())
    mono = out[0::2]
    if not mono:
        return 0.0
    peak = max(range(len(mono)), key=lambda k: abs(mono[k]))
    level = abs(mono[peak])
    if level < 3000:
        return 0.0
    onset = next(k for k in range(peak + 1) if abs(mono[k]) > level // 2)
    return context - onset / rate * tempo
