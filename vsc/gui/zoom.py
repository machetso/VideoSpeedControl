# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Fit / 1:1 / 2:1 zoom with panning, shared by the preview and the comparison view.

At 100 % one image pixel is one screen pixel (HiDPI scaling taken into account), so footage
larger than the screen can be judged at full detail.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF, Signal
from PySide6.QtWidgets import QComboBox

from ..i18n import N_, tr

ZOOMS = ((N_("Fit"), None), ("100 % (1:1)", 1.0), ("200 %", 2.0))


def fit_rect(img_w: float, img_h: float, box: QRectF) -> QRectF:
    f = min(box.width() / img_w, box.height() / img_h)
    w, h = img_w * f, img_h * f
    return QRectF(box.x() + (box.width() - w) / 2, box.y() + (box.height() - h) / 2, w, h)


class ZoomState(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom: float | None = None     # None = fit
        self.cx = self.cy = 0.5            # view centre, as fraction of the image

    def set_zoom(self, zoom: float | None, cx: float | None = None, cy: float | None = None):
        self.zoom = zoom
        if cx is not None:
            self.cx, self.cy = min(1.0, max(0.0, cx)), min(1.0, max(0.0, cy))
        self.changed.emit()

    def rect(self, img_w: int, img_h: int, box: QRectF, dpr: float) -> QRectF:
        """Where an image of img_w × img_h *native* pixels is drawn inside box."""
        if self.zoom is None:
            return fit_rect(img_w, img_h, box)
        w, h = img_w * self.zoom / dpr, img_h * self.zoom / dpr
        x = _place(box.x(), box.width(), w, self.cx)
        y = _place(box.y(), box.height(), h, self.cy)
        return QRectF(x, y, w, h)

    def pan(self, delta: QPointF, img_w: int, img_h: int, dpr: float) -> None:
        if self.zoom is None:
            return
        w, h = img_w * self.zoom / dpr, img_h * self.zoom / dpr
        self.cx = min(1.0, max(0.0, self.cx - delta.x() / w))
        self.cy = min(1.0, max(0.0, self.cy - delta.y() / h))
        self.changed.emit()

    def toggle_at(self, pos: QPointF, drawn: QRectF) -> None:
        """Double-click: fit ↔ 100 %, centred on the clicked spot."""
        if self.zoom is None and drawn.width() > 0:
            self.set_zoom(1.0, (pos.x() - drawn.x()) / drawn.width(),
                          (pos.y() - drawn.y()) / drawn.height())
        else:
            self.set_zoom(None)

    def combo(self) -> QComboBox:
        """A combo box kept in sync with this state."""
        box = QComboBox()
        box.setToolTip(tr("Zoom. At 100 % every pixel of the footage is shown 1:1 – drag to pan,\n"
                          "double-click the picture to switch between Fit and 100 %."))
        for label, z in ZOOMS:
            box.addItem(tr(label), z)
        box.currentIndexChanged.connect(lambda: self.zoom != box.currentData()
                                        and self.set_zoom(box.currentData()))

        def sync():
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(self.zoom)))
            box.blockSignals(False)
        self.changed.connect(sync)
        return box


def _place(start: float, space: float, size: float, centre: float) -> float:
    """Position of an image of `size` in `space`: centred if smaller, else panned and clamped."""
    if size <= space:
        return start + (space - size) / 2
    pos = start + space / 2 - centre * size
    return min(start, max(start + space - size, pos))
