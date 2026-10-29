# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Build the user guide: screenshots (optional) and the PDF.

The text lives in vsc/docs/manual.md – the app shows the same file (Help → User guide).

    python tools/build_docs.py                 # PDF only
    python tools/build_docs.py --screenshots   # first new screenshots, then the PDF

Screenshots use a generated clip (Mandelbrot zoom, 240 fps) – no private footage.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # never real windows (desktop may set wayland)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QMarginsF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import (QFont, QPageLayout, QPageSize, QPdfWriter, QTextBlockFormat,  # noqa: E402
                           QTextCursor, QTextDocument)
from PySide6.QtWidgets import QApplication  # noqa: E402

from vsc import __version__  # noqa: E402
from vsc.core import ffmpeg_bin  # noqa: E402
from vsc.gui import help  # noqa: E402

IMAGES = help.DOCS / "images"
WINDOW = (1200, 860)


# --------------------------------------------------------------------------- screenshots

def demo_clip(folder: Path) -> Path:
    clip = folder / "demo_240fps.mp4"
    if not clip.exists():
        print("Generating the demo clip (~40 s) …")
        subprocess.run([ffmpeg_bin.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i",
                        "mandelbrot=s=1280x720:rate=240:end_scale=0.01:start_scale=2",
                        "-t", "3", "-c:v", "libx265", "-preset", "ultrafast", "-x265-params",
                        "keyint=24:open-gop=0:log-level=error", "-pix_fmt", "yuv420p",
                        "-tag:v", "hvc1", str(clip)], check=True)
    return clip


def screenshots(app: QApplication) -> None:
    from vsc.gui.main_window import MainWindow

    work = Path(tempfile.gettempdir()) / "vsc-docs"
    work.mkdir(exist_ok=True)
    QSettings.setDefaultFormat(QSettings.IniFormat)          # keep the user's settings out
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(work / "settings"))
    clip_path = demo_clip(work)
    IMAGES.mkdir(parents=True, exist_ok=True)

    def pump(seconds=0.3):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    def wait(condition, timeout=120):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            pump(0.05)

    def shot(widget, name):
        pump(0.6)
        widget.grab().save(str(IMAGES / f"{name}.png"))
        print("  ", name)

    w = MainWindow()
    w.resize(*WINDOW)
    w.show()
    w.add_files([clip_path])
    wait(lambda: w.model.clips and w.model.clips[0].frames and w.settings.encoders is not None
         and w.model.clips[0].joins is not None and w.model.clips[0].proxy_done
         and all(w.model.clips[0].thumbs))
    clip, p, s = w.current_clip(), w.preview, w.settings
    print("Screenshots:")

    w.tabs.setCurrentIndex(2)
    shot(w, "clip_info")

    w.tabs.setCurrentIndex(0)
    p.seek(300)
    shot(w, "overview")

    # speed sections: 8× faster, original, slow motion
    s.set_process("smart")
    for a, b, fps in ((0, 239, clip.info.real_fps * 8), (240, 359, None), (360, 479, Fraction(25))):
        if fps is None:
            continue
        p.seek(a)
        p.section_start()
        p.seek(b)
        p.section_end()
        p.sec_fps.setCurrentIndex(p.sec_fps.findData(str(fps)))
        p.add_section()
    p._set_section(0, reencode=True, out_fps=Fraction(25))
    p.seek(420)
    shot(w, "sections")
    shot(s, "settings_smart")

    s.set_process("reencode")
    shot(s, "settings_reencode")
    s.set_process("lossless")
    shot(s, "settings_lossless")

    # test encode
    s.set_process("reencode")
    s.preset_combo.setCurrentIndex(s.preset_combo.findData("ultrafast"))
    w.tabs.setCurrentIndex(1)
    w.test_panel.frames_spin.setValue(24)
    p.seek(200)
    w.test_panel.run_button.click()
    wait(lambda: not clip.testing and clip.test_media is not None, 300)
    shot(w, "test_encode")

    # batch list
    s.set_process("lossless")
    p.batch_button.click()
    s.set_process("smart")
    p.batch_button.click()
    w.tabs.setCurrentIndex(3)
    w.export_panel.pattern.setText("{name}_{mode}")
    shot(w, "export")
    w.close()


# --------------------------------------------------------------------------- PDF

def build_pdf() -> None:
    writer = QPdfWriter(str(help.PDF))
    writer.setTitle("VideoSpeedControl – User guide")
    writer.setCreator(f"VideoSpeedControl {__version__}")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(5, 5, 5, 5), QPageLayout.Millimeter))   # + Qt's own 2 cm
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Noto Sans", 10))
    # no page size: print_() lays out at screen resolution, scales to the printer itself and
    # adds a 2 cm margin – pictures are limited to that text width in screen pixels (96/inch)
    text_mm = writer.pageLayout().paintRect(QPageLayout.Millimeter).width() - 2 * 20
    help.load_manual(doc, text_mm / 25.4 * 96 * 0.98, prefix=TITLE_PAGE.format(version=__version__))
    _finish_title_page(doc)
    doc.print_(writer)
    print(f"PDF written: {help.PDF} ({help.PDF.stat().st_size // 1024} KB)")


TITLE_PAGE = """![VideoSpeedControl](../gui/resources/splash.webp)

**VideoSpeedControl – User guide**

Version {version}

Copyright © 2026 Alex Vulcu. Concept, architecture, direction, and curation by Alex Vulcu. Implementation assisted by generative AI tools. Licensed under the MIT License.

"""


def _finish_title_page(doc: QTextDocument) -> None:
    """Centre the title page and start the guide on a new page; the logo at half the width."""
    block = doc.begin()
    it = block.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.charFormat().isImageFormat():
            image = frag.charFormat().toImageFormat()
            if image.width() > 0:
                image.setWidth(image.width() * 0.5)
                image.setHeight(image.height() * 0.5)
                cursor = QTextCursor(doc)
                cursor.setPosition(frag.position())
                cursor.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                cursor.setCharFormat(image)
        it += 1
    while block.isValid():
        fmt = block.blockFormat()
        fmt.setAlignment(Qt.AlignCenter)
        fmt.setTopMargin(30)
        last = block.text().startswith("Copyright ©")
        if last:
            fmt.setPageBreakPolicy(QTextBlockFormat.PageBreak_AlwaysAfter)
        QTextCursor(block).setBlockFormat(fmt)
        if last:
            return
        block = block.next()


def main() -> None:
    app = QApplication(sys.argv[:1])
    if "--screenshots" in sys.argv:
        screenshots(app)
    build_pdf()


if __name__ == "__main__":
    main()
