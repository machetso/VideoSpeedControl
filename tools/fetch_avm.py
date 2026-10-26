# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Build AVM (AV2 reference software, BSD-3-Clause-Clear, AOMedia) into vendor/avm/<platform>/.

There are no binary releases, so the tagged source is cloned and built: avmenc + avmdec only
(about 7 minutes on 8 cores). Needs git, cmake ≥ 3.16, a C/C++ compiler and nasm or yasm
(Linux: `sudo apt install cmake nasm`). Windows needs Visual Studio 2019+ – not scripted yet.

Usage:
    python tools/fetch_avm.py [--src DIR]   # reuse an existing checkout of the tag
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = "v1.0.0"
REPO = "https://github.com/AOMediaCodec/avm.git"
ROOT = Path(__file__).resolve().parent.parent
TOOLS = ("avmenc", "avmdec")


def main() -> None:
    if sys.platform == "win32":
        sys.exit("Building AVM on Windows is not scripted yet (needs Visual Studio).")
    for tool in ("git", "cmake"):
        if not shutil.which(tool):
            sys.exit(f"'{tool}' not found – install it first (e.g. sudo apt install cmake nasm)")
    if not (shutil.which("nasm") or shutil.which("yasm")):
        sys.exit("No assembler found – install nasm (sudo apt install nasm)")
    dest = ROOT / "vendor" / "avm" / "linux-x64"

    with tempfile.TemporaryDirectory(prefix="avm-") as tmp:
        if "--src" in sys.argv:
            src = Path(sys.argv[sys.argv.index("--src") + 1]).resolve()
        else:
            src = Path(tmp) / "avm"
            print(f"Cloning AVM {VERSION} ...")
            subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", VERSION, REPO,
                            str(src)], check=True)
        build = Path(tmp) / "build"
        build.mkdir()
        print("Configuring ...")
        subprocess.run(["cmake", str(src), "-DCMAKE_BUILD_TYPE=Release", "-DENABLE_TESTS=0",
                        "-DENABLE_DOCS=0", "-DENABLE_EXAMPLES=1",
                        f"-DENABLE_NASM={1 if shutil.which('nasm') else 0}"],
                       cwd=build, check=True, stdout=subprocess.DEVNULL)
        print("Building avmenc + avmdec (several minutes) ...")
        subprocess.run(["cmake", "--build", ".", "--target", *TOOLS,
                        "-j", str(os.cpu_count() or 4)], cwd=build, check=True,
                       stdout=subprocess.DEVNULL)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for tool in TOOLS:
            shutil.copy2(build / tool, dest / tool)
            (dest / tool).chmod(0o755)
        for name in ("LICENSE", "PATENTS"):
            shutil.copy2(src / name, dest / name)
        (dest / "VERSION").write_text(VERSION + "\n")
    print(f"AVM {VERSION} installed to {dest}")


if __name__ == "__main__":
    main()
