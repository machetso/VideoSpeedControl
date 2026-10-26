# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Entry point of the PyInstaller bundle (packaging/VideoSpeedControl.spec).

With VSC_SMOKE_TEST=<file> set, the bundle does not open a window but checks itself (imports,
bundled tools, user guide, icons, main window) and writes the result to <file> – the windowed
exe has no console, so CI reads the file instead of stdout.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def smoke_test(report: Path) -> int:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    from vsc.core import ffmpeg_bin, rife
    from vsc.gui import help
    from vsc.gui.main_window import MainWindow

    bundle = Path(sys._MEIPASS)
    lines, ok = [], True

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= passed
        lines.append(f"{'OK  ' if passed else 'FAIL'} {name} {detail}".rstrip())

    for tool in ("ffmpeg", "ffprobe"):
        path = Path(ffmpeg_bin.find_tool(tool))
        check(f"{tool} bundled", bundle in path.parents, str(path))
        out = subprocess.run([str(path), "-version"], capture_output=True, text=True,
                             **ffmpeg_bin.POPEN_FLAGS)
        check(f"{tool} runs", out.returncode == 0, out.stdout.split("\n", 1)[0])
    rife_dir = bundle / "vendor" / "rife" / ffmpeg_bin.PLATFORM_DIR
    check("rife bundled", (rife_dir / rife.EXE).is_file(), str(rife_dir))
    check("user guide", help.MANUAL.is_file() and help.PDF.is_file(), str(help.DOCS))
    check("icons", (help.RESOURCES / "icon_256.png").is_file(), str(help.RESOURCES))

    app = QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    check("main window", window.isVisible())
    window.close()

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    if report := os.environ.get("VSC_SMOKE_TEST"):
        sys.exit(smoke_test(Path(report)))
    from vsc.gui import main
    sys.exit(main())
