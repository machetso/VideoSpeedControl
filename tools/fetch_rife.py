# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Download rife-ncnn-vulkan (MIT, nihui) into vendor/rife/<platform>/ – binary + RIFE v4.6 model.

The release archive contains every model (~430 MB); only what the app uses is kept.

Usage:
    python tools/fetch_rife.py            # for the current platform
    python tools/fetch_rife.py windows
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "20221029"
BASE_URL = f"https://github.com/nihui/rife-ncnn-vulkan/releases/download/{VERSION}"
ASSETS = {
    "linux": f"rife-ncnn-vulkan-{VERSION}-ubuntu.zip",
    "windows": f"rife-ncnn-vulkan-{VERSION}-windows.zip",
}
MODELS = ("rife-v4.6",)
ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else ("windows" if sys.platform == "win32" else "linux")
    asset = ASSETS[target]
    dest = ROOT / "vendor" / "rife" / f"{target}-x64"
    exe = "rife-ncnn-vulkan" + (".exe" if target == "windows" else "")

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset
        print(f"Downloading {asset} (~430 MB) ...")
        urllib.request.urlretrieve(f"{BASE_URL}/{asset}", archive)
        with zipfile.ZipFile(archive) as zf:
            wanted = [n for n in zf.namelist()
                      if n.endswith("/" + exe) or n.endswith("LICENSE")
                      or any(f"/{m}/" in n for m in MODELS)]
            zf.extractall(Path(tmp) / "x", members=wanted)
        extract = Path(tmp) / "x"
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        src = next(extract.rglob(exe))
        shutil.copy2(src, dest / exe)
        (dest / exe).chmod(0o755)
        for m in MODELS:
            shutil.copytree(next(p for p in extract.rglob(m) if p.is_dir()), dest / m)
        lic = next(extract.rglob("LICENSE"), None)
        if lic:
            shutil.copy2(lic, dest / "LICENSE")
    print(f"RIFE installed to {dest}")


if __name__ == "__main__":
    main()
