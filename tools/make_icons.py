# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Make the app icons and the start-screen picture from the artwork in assets/.

  assets/VideoSpeedControl_Icon.webp → vsc/gui/resources/icon_<size>.png (16 … 512) + icon.ico
      The rounded symbol is cut out of the landscape picture, its corners made transparent.
      Sizes ≤ 64 px show only the camera – the name would not be readable there.
  assets/VideoSpeedControl_big.webp  → vsc/gui/resources/splash.webp (About dialog, PDF title)

Usage:  python tools/make_icons.py
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # never real windows (desktop may set wayland)
from PySide6.QtCore import QBuffer, QRect, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPainterPath  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
OUT = ROOT / "vsc" / "gui" / "resources"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SMALL = 64                       # up to this size: camera only
FULL_CROP = QRect(676, 84, 1400, 1360)    # the rounded symbol incl. its frame (measured)
CAMERA_CROP = QRect(918, 140, 1000, 1000)  # camera and slider, without the name
SPLASH_WIDTH = 1376


def rounded(src: QImage, size: int, radius: float) -> QImage:
    """`src` scaled to size × size with transparent rounded corners."""
    out = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius * size, radius * size)
    p.setClipPath(path)
    p.drawImage(QRectF(0, 0, size, size), src)
    p.end()
    return out


def scaled_square(img: QImage, rect: QRect, size: int, radius: float) -> QImage:
    crop = img.copy(rect)
    side = max(crop.width(), crop.height())
    square = QImage(side, side, QImage.Format_RGB32)
    square.fill(crop.pixel(2, crop.height() // 2))      # background colour of the artwork
    p = QPainter(square)
    p.drawImage((side - crop.width()) // 2, (side - crop.height()) // 2, crop)
    p.end()
    # scale in steps for a clean small result
    while square.width() > size * 2:
        square = square.scaled(square.width() // 2, square.height() // 2,
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return rounded(square, size, radius)


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
    icon = QImage(str(ASSETS / "VideoSpeedControl_Icon.webp"))
    big = QImage(str(ASSETS / "VideoSpeedControl_big.webp"))
    if icon.isNull() or big.isNull():
        sys.exit("Artwork not found in assets/ (or no WebP support in Qt)")
    images = {}
    for size in SIZES:
        rect, radius = (CAMERA_CROP, 0.2) if size <= SMALL else (FULL_CROP, 0.14)
        images[size] = scaled_square(icon, rect, size, radius)
        images[size].save(str(OUT / f"icon_{size}.png"))
    write_ico(OUT / "icon.ico", images)
    splash = big.scaledToWidth(SPLASH_WIDTH, Qt.SmoothTransformation)
    splash.save(str(OUT / "splash.webp"), "WEBP", 88)
    print(f"Icons ({', '.join(map(str, SIZES))} px), icon.ico and splash.webp written to {OUT}")


if __name__ == "__main__":
    main()
