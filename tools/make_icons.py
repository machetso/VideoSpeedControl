# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Make the app icons and the About / PDF title picture from the logo in assets/.

  assets/VSL-Logo_transparent.webp → vsc/gui/resources/icon_<size>.png (16 … 512) + icon.ico
                                   → vsc/gui/resources/splash.webp (About dialog, PDF title)
  The logo is square with a transparent background, so it is only scaled.
  (The Android icons come from the same logo: tools/make_android_icons.py.)

Usage:  python tools/make_icons.py
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # never real windows (desktop may set wayland)
from PySide6.QtCore import QBuffer, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
OUT = ROOT / "vsc" / "gui" / "resources"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SPLASH_SIZE = 1024


def scaled(img: QImage, size: int) -> QImage:
    """`img` scaled to size × size in halving steps (cleaner small icons than one big step)."""
    while img.width() > size * 2:
        img = img.scaled(img.width() // 2, img.height() // 2, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return img.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, images: dict[int, QImage]) -> None:
    """Windows .ico with PNG-compressed entries (supported since Windows Vista)."""
    entries = [(s, png_bytes(images[s])) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory, data = b"", b""
    for size, png in entries:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    path.write_bytes(header + directory + data)


def main() -> None:
    QGuiApplication(sys.argv[:1])
    OUT.mkdir(parents=True, exist_ok=True)
    logo = QImage(str(ASSETS / "VSL-Logo_transparent.webp"))
    if logo.isNull():
        sys.exit("Logo not found in assets/ (or no WebP support in Qt)")
    logo = logo.convertToFormat(QImage.Format_ARGB32)
    images = {}
    for size in SIZES:
        images[size] = scaled(logo, size)
        images[size].save(str(OUT / f"icon_{size}.png"))
    write_ico(OUT / "icon.ico", images)
    scaled(logo, SPLASH_SIZE).save(str(OUT / "splash.webp"), "WEBP", 90)
    print(f"Icons ({', '.join(map(str, SIZES))} px), icon.ico and splash.webp written to {OUT}")


if __name__ == "__main__":
    main()
