# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Make the Android launcher icon and in-app logo from assets/VideoSpeedControl_0.92_big.webp.

The artwork is a gauge on a colour gradient. Android launcher icons are adaptive (two 108 dp
layers, cut to a circle / squircle / … by the launcher), so the picture is split:
  * background layer: the gradient alone – a smooth polynomial fitted to the visible gradient,
    stretched to the whole layer;
  * foreground layer: the gauge, cut out (its drop shadow kept as translucent black), scaled so
    it fits into the area every launcher mask shows.
  * drawable-nodpi/vsc_logo.png: the icon as a rounded square for the app's title bar.

Usage:  python tools/make_android_icons.py
"""
from __future__ import annotations

import os
import sys
from collections import deque
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPainterPath  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "VideoSpeedControl_0.92_big.webp"
RES = ROOT / "android" / "app" / "src" / "main" / "res"
WORK = 1024                       # working resolution of the cut-out
FIT = 128                         # resolution of the gradient fit
DEGREE = 4
CORE_DIFF = 40                    # colour distance from the gradient that counts as gauge
LAYER_DP = 108
GAUGE_RADIUS_DP = 34              # farthest gauge pixel from the centre (visible circle: 36 dp)
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
LOGO_SIZE = 192


def rgb_rows(img: QImage) -> list[bytes]:
    img = img.convertToFormat(QImage.Format_RGB888)
    bpl, raw = img.bytesPerLine(), bytes(img.constBits())
    return [raw[y * bpl: y * bpl + img.width() * 3] for y in range(img.height())]


def terms(u: float, v: float) -> list[float]:
    return [u ** i * v ** j for i in range(DEGREE + 1) for j in range(DEGREE + 1 - i)]


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(a)
    m = [a[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_gradient(img: QImage) -> QImage:
    """FIT × FIT picture of the background gradient (gauge removed)."""
    rows = rgb_rows(img.scaled(FIT, FIT, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    px = lambda x, y: rows[y][3 * x: 3 * x + 3]  # noqa: E731
    n = FIT
    # pixels that surely show the gradient: top / bottom bands and the corners
    pts = [(x, y) for y in range(n) for x in range(n)
           if y < n * 0.08 or y > n * 0.93 or ((x < n * 0.12 or x > n * 0.88) and (y < n * 0.2 or y > n * 0.82))]
    coefs: list[list[float]] = []
    for _ in range(3):                      # refit without the outliers (shadow, gauge edges)
        coefs = []
        for ch in range(3):
            k = len(terms(0, 0))
            a, b = [[0.0] * k for _ in range(k)], [0.0] * k
            for x, y in pts:
                t = terms(x / n * 2 - 1, y / n * 2 - 1)
                for i in range(k):
                    b[i] += t[i] * px(x, y)[ch]
                    for j in range(k):
                        a[i][j] += t[i] * t[j]
            coefs.append(solve(a, b))
        model = lambda x, y: [sum(c * t for c, t in zip(coefs[ch], terms(x / n * 2 - 1, y / n * 2 - 1)))  # noqa: E731
                              for ch in range(3)]
        pts = [(x, y) for x, y in pts if max(abs(m - p) for m, p in zip(model(x, y), px(x, y))) < 10]
    out = QImage(n, n, QImage.Format_RGB32)
    for y in range(n):
        for x in range(n):
            r, g, b = (max(0, min(255, round(c))) for c in model(x, y))
            out.setPixel(x, y, 0xFF000000 | r << 16 | g << 8 | b)
    return out


def cut_out(img: QImage, gradient: QImage) -> QImage:
    """The gauge on transparency: inside its outline the original pixels, outside only the
    darkening of its drop shadow (as translucent black, so it falls on any background)."""
    n = WORK
    src = rgb_rows(img.scaled(n, n, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    bg = rgb_rows(gradient.scaled(n, n, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    core = bytearray(n * n)
    for y in range(n):
        s, b = src[y], bg[y]
        for x in range(n):
            i = 3 * x
            if max(abs(s[i] - b[i]), abs(s[i + 1] - b[i + 1]), abs(s[i + 2] - b[i + 2])) > CORE_DIFF:
                core[y * n + x] = 1
    # fill the holes: everything the outside cannot reach is gauge (film perforations included)
    outside = bytearray(n * n)
    queue = deque(i for i in range(n * n) if (i < n or i >= n * (n - 1) or i % n in (0, n - 1)) and not core[i])
    for i in queue:
        outside[i] = 1
    while queue:
        i = queue.popleft()
        x, y = i % n, i // n
        for j in ((i - 1) if x > 0 else -1, (i + 1) if x < n - 1 else -1, i - n, i + n):
            if 0 <= j < n * n and not outside[j] and not core[j]:
                outside[j] = 1
                queue.append(j)
    out = QImage(n, n, QImage.Format_ARGB32)
    for y in range(n):
        s, b = src[y], bg[y]
        for x in range(n):
            i = 3 * x
            if not outside[y * n + x]:
                out.setPixel(x, y, 0xFF000000 | s[i] << 16 | s[i + 1] << 8 | s[i + 2])
            else:
                lum = 0.299 * s[i] + 0.587 * s[i + 1] + 0.114 * s[i + 2]
                lum_bg = 0.299 * b[i] + 0.587 * b[i + 1] + 0.114 * b[i + 2]
                a = max(0, min(255, round(255 * (1 - lum / max(lum_bg, 1)))))
                out.setPixel(x, y, a << 24 if a > 3 else 0)
    return out


def farthest(cut: QImage) -> float:
    """Distance of the farthest opaque gauge pixel from the centre, as a fraction of the width."""
    n, c = cut.width(), cut.width() / 2
    best = 0.0
    for y in range(0, n, 2):
        for x in range(0, n, 2):
            if cut.pixel(x, y) >> 24 == 255:
                best = max(best, ((x - c) ** 2 + (y - c) ** 2) ** 0.5)
    return best / n


def layer(size: int, draw) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    draw(p)
    p.end()
    return img


def main() -> None:
    QGuiApplication(sys.argv[:1])
    art = QImage(str(SOURCE))
    if art.isNull():
        sys.exit(f"{SOURCE} not found (or no WebP support in Qt)")
    gradient = fit_gradient(art)
    cut = cut_out(art, gradient)
    scale_dp = GAUGE_RADIUS_DP / farthest(cut)          # width of the artwork in the layer, in dp
    print(f"artwork drawn {scale_dp:.1f} dp wide in the {LAYER_DP} dp layer")
    smooth_bg = gradient.scaled(512, 512, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    for name, d in DENSITIES.items():
        size = round(LAYER_DP * d)
        folder = RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ic_launcher.png").unlink(missing_ok=True)     # old non-adaptive icon
        w = scale_dp * d
        fg = layer(size, lambda p: p.drawImage(QRectF((size - w) / 2, (size - w) / 2, w, w), cut))
        fg.save(str(folder / "ic_launcher_foreground.png"))
        bg = layer(size, lambda p: p.drawImage(QRectF(0, 0, size, size), smooth_bg))
        bg.convertToFormat(QImage.Format_RGB32).save(str(folder / "ic_launcher_background.png"))
    # title bar logo: the launcher icon as a rounded square (the cut-out alone shows the shadow
    # baked into the gauge's edge on dark backgrounds)
    visible = LOGO_SIZE * LAYER_DP / 72                  # the launcher shows the inner 72 dp

    def draw_logo(p: QPainter) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, LOGO_SIZE, LOGO_SIZE), LOGO_SIZE * 0.3, LOGO_SIZE * 0.3)
        p.setClipPath(path)
        off = (LOGO_SIZE - visible) / 2
        p.drawImage(QRectF(off, off, visible, visible), smooth_bg)
        w = scale_dp / LAYER_DP * visible
        p.drawImage(QRectF((LOGO_SIZE - w) / 2, (LOGO_SIZE - w) / 2, w, w), cut)

    (RES / "drawable-nodpi").mkdir(exist_ok=True)
    layer(LOGO_SIZE, draw_logo).save(str(RES / "drawable-nodpi" / "vsc_logo.png"))
    print(f"launcher layers ({', '.join(DENSITIES)}) and drawable-nodpi/vsc_logo.png written to {RES}")


if __name__ == "__main__":
    main()
