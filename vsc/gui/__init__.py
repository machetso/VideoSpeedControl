"""PySide6 user interface."""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("VideoSpeedControl")
    app.setOrganizationName("VideoSpeedControl")   # QSettings → ~/.config/VideoSpeedControl/
    app.setDesktopFileName("videospeedcontrol")   # Wayland: matches the launcher entry's icon
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.svg"))))
    window = MainWindow()
    window.add_files([Path(a) for a in argv[1:]])
    window.show()
    return app.exec()
