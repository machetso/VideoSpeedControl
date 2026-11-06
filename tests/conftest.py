# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Shared fixtures. Test clips are generated on first run (tests/media)."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

# stored previews of the test clips go to a temporary cache, never into the user's
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="vsc-test-cache-")
os.environ["LOCALAPPDATA"] = os.environ["XDG_CACHE_HOME"]
# the interface language is English in tests (the developer's computer is German) – i18n tests
# switch it explicitly
os.environ["VSC_LANG"] = "en"

import pytest

from vsc.core import encoders, ffmpeg_bin

MEDIA = Path(__file__).parent / "media"


def _make(name: str, args: list[str]) -> Path:
    p = MEDIA / name
    if not p.exists():
        MEDIA.mkdir(exist_ok=True)
        subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-y", *args, str(p)], check=True)
    return p


@pytest.fixture(scope="session")
def h264_clip() -> Path:
    return _make("h264_240.mp4", [
        "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=240000/1001:d=4",
        "-f", "lavfi", "-i", "sine=f=440:d=4", "-c:v", "libx264", "-preset", "veryfast",
        "-g", "24", "-bf", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"])


@pytest.fixture(scope="session")
def hevc10_clip() -> Path:
    return _make("hevc10_240.mp4", [
        "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=240:d=2", "-c:v", "libx265",
        "-preset", "ultrafast", "-x265-params", "keyint=30:log-level=error",
        "-pix_fmt", "yuv420p10le"])


@pytest.fixture(scope="session")
def encoder_status():
    return encoders.detect()


@pytest.fixture(scope="session")
def hevc_closed_clip() -> Path:
    """HEVC with closed GOPs (IDR keyframes) – like phone footage; smart re-encode can join it."""
    return _make("hevc_closed_240.mp4", [
        "-f", "lavfi", "-i", "testsrc2=s=640x360:r=240:d=1", "-c:v", "libx265",
        "-preset", "ultrafast", "-x265-params", "keyint=24:min-keyint=24:open-gop=0:log-level=error",
        "-pix_fmt", "yuv420p", "-tag:v", "hvc1"])
