# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""The C port of Media3's Sonic is bit-exact with the Java original used by the Android app.

The reference hashes come from the Java original (tools/sonic_reference/); regenerate with
`python tests/test_sonic.py --regenerate PATH/TO/JAVA/CLASSES`.
"""
from __future__ import annotations

import hashlib
import math
import random
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vsc.core import sonic  # noqa: E402

# (speed, input rate, output rate, channels): slow-downs incl. 40×, speed-ups, mono, 44.1 kHz,
# and the resampling Android uses for phone slow-mo (input rate × slow-mo factor → 48 kHz)
CASES = [
    (0.125, 48000, 48000, 2), (0.025, 48000, 48000, 2), (0.5, 48000, 48000, 2),
    (0.7, 48000, 48000, 2), (1.5, 48000, 48000, 2), (3.0, 48000, 48000, 2),
    (0.25, 44100, 44100, 1), (0.125, 192000, 48000, 2), (1.0, 96000, 48000, 2),
]
REFERENCE = {   # from Media3 1.11.1's Sonic.java (length in bytes, SHA-256)
    "0.125@48000->48000x2": (2303992, "57f66c602362de708711200093cab92b280381bf1067ed5e9981b9522a868280"),
    "0.025@48000->48000x2": (11519968, "6a9cb8391390d931c499c928618731687715aca8c976212c60f7734f84c997e9"),
    "0.5@48000->48000x2": (576000, "09056d0a6c2ecc8e61af71a4eb4aae1213ca9ba0a1975ba5daa6299d9c34b204"),
    "0.7@48000->48000x2": (411428, "62e11ca8249b8d04eba1beaeafa330216f74397c6650e83edee96663de62b630"),
    "1.5@48000->48000x2": (192000, "099a493db650db0fa1592f3935dad5145da8b7aca9ce259bf3d5e8c31c6ee680"),
    "3.0@48000->48000x2": (96000, "6e7756e320b9fb86b7ea1434a125e10b29337033b65d1c03d39461f17b3b20a3"),
    "0.25@44100->44100x1": (529202, "bb138a78b7caabe4d90400bff08f028882831778c52f5e79dcf5aaa1cff58040"),
    "0.125@192000->48000x2": (2304000, "01c5d0852729d78830da91f2f7cebce7d64b6ddb945ffc5dac838aca9867f4db"),
    "1.0@96000->48000x2": (288004, "5ecd942a15d45bc6a2fa5483541f2d6730db88d70cbe44dde98f645491e5b209"),
}


def signal(rate: int, channels: int, seconds: float = 1.5) -> bytes:
    """Deterministic test sound: two tones with a glide, noise, and a click every 0.3 s."""
    rnd = random.Random(1234)
    out = []
    for i in range(int(rate * seconds)):
        t = i / rate
        v = 0.3 * math.sin(2 * math.pi * 220 * t) + 0.2 * math.sin(2 * math.pi * (300 + 200 * t) * t)
        v += 0.05 * (rnd.random() - 0.5)
        if (i % int(rate * 0.3)) < rate // 2000:
            v += 0.8
        s = max(-32768, min(32767, int(v * 20000)))
        out.extend([s, s // 2 if channels > 1 else s][:channels])
    return struct.pack(f"<{len(out)}h", *out)


def c_port(pcm: bytes, speed: float, rate: int, out_rate: int, channels: int, chunk: int) -> bytes:
    """Run the C port, feeding `chunk` frames at a time (output must not depend on chunking)."""
    fb = 2 * channels
    with sonic.Stream(rate, channels, speed, out_rate) as s:
        out = bytearray()
        for i in range(0, len(pcm), chunk * fb):
            s.write(pcm[i:i + chunk * fb])
            out += s.read()
        out += s.flush()
    return bytes(out)


def key(case) -> str:
    return "{}@{}->{}x{}".format(*case)


@pytest.mark.skipif(sonic.unavailable_reason() is not None, reason="Sonic library not built")
@pytest.mark.parametrize("case", CASES, ids=key)
def test_bit_exact_with_media3(case):
    speed, rate, out_rate, ch = case
    pcm = signal(rate, ch)
    want = REFERENCE[key(case)]
    for chunk in (1024, 333, 100000):
        got = c_port(pcm, speed, rate, out_rate, ch, chunk)
        assert (len(got), hashlib.sha256(got).hexdigest()) == want, f"chunk {chunk}"


def regenerate(classes: str) -> None:
    """Print a new REFERENCE table from the Java original (needs `java` on PATH)."""
    with tempfile.TemporaryDirectory() as tmp:
        for case in CASES:
            speed, rate, out_rate, ch = case
            src, dst = Path(tmp, "in.s16"), Path(tmp, "out.s16")
            src.write_bytes(signal(rate, ch))
            subprocess.run(["java", "-cp", classes, "androidx.media3.common.audio.Run", str(src),
                            str(dst), str(speed), str(rate), str(out_rate), str(ch), "1024"],
                           check=True)
            data = dst.read_bytes()
            print(f'    "{key(case)}": ({len(data)}, "{hashlib.sha256(data).hexdigest()}"),')


if __name__ == "__main__" and "--regenerate" in sys.argv:
    regenerate(sys.argv[sys.argv.index("--regenerate") + 1])
