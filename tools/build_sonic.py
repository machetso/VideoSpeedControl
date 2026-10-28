# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Build the Sonic time-stretching library into vendor/sonic/<platform>-x64/.

native/sonic_media3/sonic_media3.c is a C port of Media3's Sonic – the exact algorithm the
Android app uses, so both apps sound the same (bit-exact, see tests/test_sonic.py). Apache-2.0.
Needs a C compiler: Linux gcc / cc, Windows gcc (MinGW, on the GitHub runners) or MSVC `cl`.

Usage:
    python tools/build_sonic.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "native" / "sonic_media3"


def main() -> None:
    windows = sys.platform == "win32"
    dest = ROOT / "vendor" / "sonic" / ("windows-x64" if windows else "linux-x64")
    lib = dest / ("sonic.dll" if windows else "libsonic.so")
    with tempfile.TemporaryDirectory(prefix="sonic-") as tmp:
        out = Path(tmp) / lib.name
        c = SRC / "sonic_media3.c"
        cc = shutil.which("gcc") or shutil.which("cc")
        if cc:
            # -ffp-contract=off: no fused multiply-add, so float results match Java exactly
            args = [cc, "-O2", "-ffp-contract=off", "-shared", "-o", str(out), str(c)]
            args += ["-static-libgcc"] if windows else ["-fPIC", "-fvisibility=hidden", "-lm"]
        elif windows and shutil.which("cl"):
            args = ["cl", "/nologo", "/O2", "/fp:precise", "/LD", str(c), f"/Fe:{out}"]
        else:
            sys.exit("No C compiler found (gcc / cc, or MSVC cl on Windows).")
        subprocess.run(args, check=True, cwd=tmp)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, lib)
        shutil.copy2(SRC / "LICENSE", dest / "LICENSE")
    print(f"Done: {lib}")


if __name__ == "__main__":
    main()
