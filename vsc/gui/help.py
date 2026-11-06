# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""App icon, user guide window and About dialog.

The user guide is one Markdown file (vsc/docs/manual.md with its pictures); the same text is
shown in the app and turned into the PDF by tools/build_docs.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from .. import __version__
from ..i18n import tr

RESOURCES = Path(__file__).with_name("resources")
DOCS = Path(__file__).resolve().parent.parent / "docs"
MANUAL = DOCS / "manual.md"
PDF = DOCS / "VideoSpeedControl_Manual.pdf"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)

ATTRIBUTION = ("Concept, architecture, direction, and curation by Alex Vulcu.<br>"
               "Implementation assisted by generative AI tools.")


def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        path = RESOURCES / f"icon_{size}.png"
        if path.is_file():
            icon.addFile(str(path), QSize(size, size))
    return icon


def splash_pixmap(width: int) -> QPixmap:
    pix = QPixmap(str(RESOURCES / "splash.webp"))
    return pix.scaledToWidth(width, Qt.SmoothTransformation) if not pix.isNull() else pix


# --------------------------------------------------------------------------- user guide

def load_manual(doc: QTextDocument, max_image_width: float,
                prefix: str = "") -> list[tuple[int, str]]:
    """Fill `doc` with the user guide; returns (level, title) of every heading."""
    text = MANUAL.read_text(encoding="utf-8") if MANUAL.is_file() else "# " + tr("User guide missing")
    doc.setBaseUrl(QUrl.fromLocalFile(str(DOCS) + "/"))
    doc.setMarkdown(prefix + text, QTextDocument.MarkdownDialectGitHub)
    fit_images(doc, max_image_width)
    return [(len(m.group(1)), m.group(2).strip())
            for m in re.finditer(r"^(#{1,3})\s+(.+)$", text, re.M)]


def fit_images(doc: QTextDocument, max_width: float) -> None:
    """Load the pictures into `doc`; scale those wider than `max_width` down to it."""
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            fmt = frag.charFormat()
            if fmt.isImageFormat():
                image = fmt.toImageFormat()
                pix = QPixmap(str(DOCS / image.name()))
                # stored in the document: a printed copy can not load it from the path
                doc.addResource(QTextDocument.ImageResource, QUrl(image.name()), pix.toImage())
                if not pix.isNull() and pix.width() > max_width:
                    image.setWidth(max_width)
                    image.setHeight(pix.height() * max_width / pix.width())
                    cursor = QTextCursor(doc)
                    cursor.setPosition(frag.position())
                    cursor.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                    cursor.setCharFormat(image)
            it += 1
        block = block.next()


class HelpWindow(QDialog):
    """The user guide with a list of chapters on the left."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("VideoSpeedControl – User guide"))
        self.resize(1100, 780)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.headings = load_manual(self.browser.document(), 820)
        self.toc = QListWidget()
        for level, title in self.headings:
            self.toc.addItem(("    " * (level - 1)) + title)
        self.toc.currentRowChanged.connect(self._jump)
        pdf = QLabel(f"<a href='{QUrl.fromLocalFile(str(PDF)).toString()}'>{tr('Open as PDF')}</a>")
        pdf.setOpenExternalLinks(True)
        pdf.setVisible(PDF.is_file())
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toc, 1)
        lay.addWidget(pdf)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.browser)
        split.setSizes([260, 840])
        layout = QVBoxLayout(self)
        layout.addWidget(split)

    def _jump(self, row: int) -> None:
        if row < 0:
            return
        title = self.headings[row][1]
        doc = self.browser.document()
        cursor = doc.find(title, 0, QTextDocument.FindCaseSensitively)
        while not cursor.isNull() and cursor.block().blockFormat().headingLevel() == 0:
            cursor = doc.find(title, cursor, QTextDocument.FindCaseSensitively)
        if cursor.isNull():
            return
        cursor.clearSelection()
        self.browser.setTextCursor(cursor)
        bar = self.browser.verticalScrollBar()
        bar.setValue(bar.value() + self.browser.cursorRect().top() - 8)


def open_pdf() -> bool:
    return PDF.is_file() and QDesktopServices.openUrl(QUrl.fromLocalFile(str(PDF)))


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("About VideoSpeedControl"))
        picture = QLabel()
        picture.setPixmap(splash_pixmap(260))
        picture.setAlignment(Qt.AlignCenter)
        text = QLabel(
            f"<h2>VideoSpeedControl {__version__}</h2>"
            "<p>" + tr("Full control over the speed of a video clip: split a native slow-motion "
                       "clip into sections, each with its own frame rate – exported losslessly as "
                       "a variable-frame-rate clip, with a smart re-encode of only the changed "
                       "sections, or fully re-encoded in a codec of your choice.") + "</p>"
            f"<p>Copyright © 2026 Alex Vulcu<br>{ATTRIBUTION}</p>"
            "<p>" + tr("Licensed under the MIT License. Bundled tools keep their own licences "
                       "(FFmpeg: GPL, Qt / PySide6: LGPL, rife-ncnn-vulkan: MIT, AVM: "
                       "BSD-3-Clause-Clear) – see LICENSE and THIRD_PARTY_NOTICES.md.") + "</p>")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(picture)
        layout.addWidget(text)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)
