# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Make the Android launcher icon and in-app logo from assets/VSL-Logo_transparent.webp.

Android launcher icons are adaptive: two 108 dp layers, cut to a circle / squircle / … by the
launcher. Background: a dark blue radial gradient (the dial's colour, chosen by the user).
Foreground: the logo, scaled so its farthest pixel lies 34 dp from the centre – inside the
72 dp every launcher mask shows. drawable-nodpi/vsc_logo.png: the logo (transparent) for the
app's title bar.

Usage:  python tools/make_android_icons.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QRadialGradient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "VSL-Logo_transparent.webp"
RES = ROOT / "android" / "app" / "src" / "main" / "res"
LAYER_DP = 108
LOGO_RADIUS_DP = 34
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
GRADIENT = ("#3a4a6b", "#141a26")        # centre (a little above the middle) → edge
LOGO_SIZE = 192


def farthest(img: QImage) -> float:
    """Distance of the farthest opaque pixel from the centre, as a fraction of the width."""
    n = 512
    small = img.scaled(n, n, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    c = n / 2
    return max(((x - c) ** 2 + (y - c) ** 2) ** 0.5
               for y in range(n) for x in range(n) if small.pixel(x, y) >> 24 > 128) / n


def layer(size: int, draw) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    draw(p)
    p.end()
    return img


def background(p: QPainter, size: int) -> None:
    g = QRadialGradient(QPointF(size / 2, size * 0.4), size * 0.75)
    g.setColorAt(0, QColor(GRADIENT[0]))
    g.setColorAt(1, QColor(GRADIENT[1]))
    p.fillRect(QRectF(0, 0, size, size), g)


def main() -> None:
    QGuiApplication(sys.argv[:1])
    logo = QImage(str(SOURCE))
    if logo.isNull():
        sys.exit(f"{SOURCE} not found (or no WebP support in Qt)")
    width_dp = LOGO_RADIUS_DP / farthest(logo)
    print(f"logo drawn {width_dp:.1f} dp wide in the {LAYER_DP} dp layer")
    for name, d in DENSITIES.items():
        size = round(LAYER_DP * d)
        folder = RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        w = width_dp * d
        fg = layer(size, lambda p: p.drawImage(QRectF((size - w) / 2, (size - w) / 2, w, w), logo))
        fg.save(str(folder / "ic_launcher_foreground.png"))
        bg = layer(size, lambda p: background(p, size))
        bg.convertToFormat(QImage.Format_RGB32).save(str(folder / "ic_launcher_background.png"))
    (RES / "drawable-nodpi").mkdir(exist_ok=True)
    logo.scaled(LOGO_SIZE, LOGO_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation) \
        .save(str(RES / "drawable-nodpi" / "vsc_logo.png"))
    print(f"launcher layers ({', '.join(DENSITIES)}) and drawable-nodpi/vsc_logo.png written to {RES}")


if __name__ == "__main__":
    main()
