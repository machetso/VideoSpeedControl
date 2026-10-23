"""Locate the bundled ffmpeg/ffprobe binaries and run them without console windows."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
EXE = ".exe" if IS_WINDOWS else ""
PLATFORM_DIR = "windows-x64" if IS_WINDOWS else "linux-x64"

# Hide the console window that Windows would open for every ffmpeg call.
POPEN_FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}


def _candidate_dirs() -> list[Path]:
    dirs = []
    if env := os.environ.get("VSC_FFMPEG_DIR"):
        dirs.append(Path(env))
    if hasattr(sys, "_MEIPASS"):  # PyInstaller bundle
        dirs.append(Path(sys._MEIPASS) / "vendor" / "ffmpeg" / PLATFORM_DIR)
    project_root = Path(__file__).resolve().parents[2]
    dirs.append(project_root / "vendor" / "ffmpeg" / PLATFORM_DIR)
    return dirs


@cache
def find_tool(name: str) -> str:
    """Return the path of ffmpeg/ffprobe: bundled copy first, then PATH."""
    for d in _candidate_dirs():
        p = d / f"{name}{EXE}"
        if p.is_file():
            return str(p)
    if found := shutil.which(name):
        return found
    raise FileNotFoundError(
        f"{name} not found. Run 'python tools/fetch_ffmpeg.py' or install FFmpeg."
    )


def ffmpeg() -> str:
    return find_tool("ffmpeg")


def ffprobe() -> str:
    return find_tool("ffprobe")


def run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run a tool and capture text output (UTF-8, errors replaced)."""
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, **POPEN_FLAGS,
    )
