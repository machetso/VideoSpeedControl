# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""PyInstaller spec – one-folder bundle with FFmpeg, RIFE (and AVM if present).

    python tools/fetch_ffmpeg.py && python tools/fetch_rife.py
    pyinstaller packaging/VideoSpeedControl.spec --noconfirm   →   dist/VideoSpeedControl/

The bundled tools land in <bundle>/vendor/<tool>/<platform>-x64/, where vsc.core looks for them
via sys._MEIPASS. AVM (AV2) is included only if vendor/avm/<platform>-x64 exists.
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
WINDOWS = sys.platform == "win32"
PLATFORM_DIR = "windows-x64" if WINDOWS else "linux-x64"


def tree(src: Path, dest: str) -> list[tuple[str, str]]:
    """(file, target folder) pairs for every file below src, keeping sub-folders."""
    return [(str(f), str(Path(dest) / f.parent.relative_to(src)))
            for f in sorted(src.rglob("*")) if f.is_file()]


datas = tree(ROOT / "vsc" / "gui" / "resources", "vsc/gui/resources")
datas += tree(ROOT / "vsc" / "docs", "vsc/docs")
datas += [(str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")]

for tool, required in (("ffmpeg", True), ("rife", True), ("avm", False)):
    src = ROOT / "vendor" / tool / PLATFORM_DIR
    if src.is_dir():
        datas += tree(src, f"vendor/{tool}/{PLATFORM_DIR}")
    elif required:
        raise SystemExit(f"{src} missing – run tools/fetch_{tool}.py first")

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoSpeedControl",
    icon=str(ROOT / "vsc" / "gui" / "resources" / "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="VideoSpeedControl", upx=False)
