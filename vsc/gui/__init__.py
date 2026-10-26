# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""PySide6 user interface."""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from . import help
    from .main_window import MainWindow

    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("VideoSpeedControl")
    app.setOrganizationName("VideoSpeedControl")   # QSettings → ~/.config/VideoSpeedControl/
    app.setDesktopFileName("videospeedcontrol")   # Wayland: matches the launcher entry's icon
    app.setWindowIcon(help.app_icon())
    window = MainWindow()
    window.add_files([Path(a) for a in argv[1:]])
    window.show()
    return app.exec()
