# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Build the Android user guide PDFs from android/docs/manual.md (English) and manual_de.md
(German), like tools/build_docs.py.

    .venv/bin/python android/tools/build_manual.py          # both
    .venv/bin/python android/tools/build_manual.py de       # only the German one

Title page: the logo (vsc/gui/resources/splash.webp, made from assets/VSL-Logo_transparent.webp),
the version from android/app/build.gradle.kts and the copyright.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # never real windows (desktop may set wayland)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from PySide6.QtCore import QMarginsF, QUrl  # noqa: E402
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from build_docs import _finish_title_page  # noqa: E402
from vsc.gui import help  # noqa: E402

DOCS = ROOT / "android" / "docs"
LOGO = ROOT / "vsc" / "gui" / "resources" / "splash.webp"

# language → (text, PDF, title, title page); the title page's last line must start with "Copyright ©"
GUIDES = {
    "en": ("manual.md", "VideoSpeedControl_Android_Guide.pdf", "VideoSpeedControl for Android – User guide",
           "Copyright © 2026 Alex Vulcu. Concept, architecture, direction, and curation by Alex Vulcu. "
           "Implementation assisted by generative AI tools. Licensed under the MIT License."),
    "de": ("manual_de.md", "VideoSpeedControl_Android_Anleitung.pdf", "VideoSpeedControl für Android – Anleitung",
           "Copyright © 2026 Alex Vulcu. Konzept, Architektur, Leitung und Kuratierung: Alex Vulcu. "
           "Bei der Umsetzung wurden generative KI-Werkzeuge eingesetzt. Lizenziert unter der MIT-Lizenz."),
}

TITLE_PAGE = """![VideoSpeedControl]({logo})

**{title}**

Version {version}

{copyright}

"""


def version() -> str:
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    return re.search(r'versionName\s*=\s*"([^"]+)"', gradle).group(1)


def build_pdf(lang: str) -> None:
    text, pdf, title, copyright = GUIDES[lang]
    out = DOCS / pdf
    writer = QPdfWriter(str(out))
    writer.setTitle(title)
    writer.setCreator(f"VideoSpeedControl {version()}")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(5, 5, 5, 5), QPageLayout.Millimeter))   # + Qt's own 2 cm
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Noto Sans", 10))
    doc.setBaseUrl(QUrl.fromLocalFile(str(DOCS) + "/"))
    logo = os.path.relpath(LOGO, DOCS)
    doc.setMarkdown(TITLE_PAGE.format(logo=logo, title=title, version=version(), copyright=copyright)
                    + (DOCS / text).read_text(encoding="utf-8"), QTextDocument.MarkdownDialectGitHub)
    # pictures are limited to the text width in screen pixels (see tools/build_docs.py)
    text_mm = writer.pageLayout().paintRect(QPageLayout.Millimeter).width() - 2 * 20
    help.DOCS = DOCS                      # fit_images loads the pictures relative to this folder
    help.fit_images(doc, text_mm / 25.4 * 96 * 0.98)
    _finish_title_page(doc)
    doc.print_(writer)
    print(f"PDF written: {out} ({out.stat().st_size // 1024} KB)")


def main() -> None:
    QApplication(sys.argv[:1])
    for lang in sys.argv[1:] or GUIDES:
        build_pdf(lang)


if __name__ == "__main__":
    main()
