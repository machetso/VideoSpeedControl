"""Download a static GPL FFmpeg build (BtbN) into vendor/ffmpeg/<platform>/.

Usage:
    python tools/fetch_ffmpeg.py            # for the current platform
    python tools/fetch_ffmpeg.py windows    # e.g. to prepare a Windows build on Linux
"""
from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

FFMPEG_SERIES = "n9.0"
BASE_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
ASSETS = {
    "linux": f"ffmpeg-{FFMPEG_SERIES}-latest-linux64-gpl-{FFMPEG_SERIES[1:]}.tar.xz",
    "windows": f"ffmpeg-{FFMPEG_SERIES}-latest-win64-gpl-{FFMPEG_SERIES[1:]}.zip",
}
ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else ("windows" if sys.platform == "win32" else "linux")
    asset = ASSETS[target]
    dest = ROOT / "vendor" / "ffmpeg" / f"{target}-x64"
    exe = ".exe" if target == "windows" else ""

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset
        print(f"Downloading {asset} ...")
        urllib.request.urlretrieve(f"{BASE_URL}/{asset}", archive)

        extract_dir = Path(tmp) / "x"
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_dir)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(extract_dir, filter="data")

        dest.mkdir(parents=True, exist_ok=True)
        for name in ("ffmpeg", "ffprobe"):
            src = next(extract_dir.rglob(f"bin/{name}{exe}"))
            shutil.copy2(src, dest / f"{name}{exe}")
            (dest / f"{name}{exe}").chmod(0o755)
        lic = next(extract_dir.rglob("LICENSE.txt"), None)
        if lic:
            shutil.copy2(lic, dest / "LICENSE.txt")
    print(f"FFmpeg installed to {dest}")


if __name__ == "__main__":
    main()
