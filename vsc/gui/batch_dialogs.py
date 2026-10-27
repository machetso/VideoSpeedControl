# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Dialogs of the batch list: open an entry (edit it or add another encoding) and the name
additions that tell several encodings of one clip apart."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox,
                               QVBoxLayout, QWidget)

from ..core import batch
from ..core.job import Job, output_path

NEW, EDIT = "new", "edit"
_KEY = "batch/additions"


def ask_entry_action(parent: QWidget, label: str) -> str | None:
    """NEW = another encoding of the clip, EDIT = change this entry, None = cancelled."""
    box = QMessageBox(parent)
    box.setWindowTitle("Batch entry")
    box.setIcon(QMessageBox.Question)
    box.setText(f"Open “{label}”?")
    box.setInformativeText(
        "Its sections, trim and settings are loaded into Preview & trim (the clip's current "
        "sections can be brought back with ↶ Undo).\n\n"
        "Another encoding: change what you like, then “➕ Add to batch” adds it as a new entry "
        "– you can add the codec, preset, quality or resolution to its file name.\n"
        "Edit this entry: “✔ Update batch entry” replaces this entry.")
    new = box.addButton("Another encoding", QMessageBox.AcceptRole)
    edit = box.addButton("Edit this entry", QMessageBox.AcceptRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(new)
    box.exec()
    return {new: NEW, edit: EDIT}.get(box.clickedButton())


def _stored() -> set[str]:
    """Name additions chosen last time (all of them the first time)."""
    stored = QSettings().value(_KEY, None)
    return set(stored.split(",")) if isinstance(stored, str) else {k for k, _ in batch.ADDITIONS}


class AdditionDialog(QDialog):
    """Asks before another encoding of a clip goes into the batch list; checkboxes for the
    parts added to its file name, with a live preview of the name."""

    def __init__(self, parent: QWidget, job: Job, count: int, pattern: str,
                 folder: Path | None):
        super().__init__(parent)
        self.setWindowTitle("Another encoding")
        self.job, self.pattern = job, pattern
        self.folder = folder or job.info.path.parent
        name = job.info.path.name
        intro = QLabel(f"{name} is already in the batch list "
                       f"({count} encoding{'s' * (count != 1)}).\n"
                       "Add this as another encoding? Add these to its file name:")
        intro.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)

        chosen = _stored()
        parts = batch.addition_parts(job)
        self.boxes: dict[str, QCheckBox] = {}
        for key, label in batch.ADDITIONS:
            value = parts[key]
            box = QCheckBox(f"{label}: {value}" if value else f"{label} (not used here)")
            box.setEnabled(bool(value))
            box.setChecked(bool(value) and key in chosen)
            box.toggled.connect(self._update)
            layout.addWidget(box)
            self.boxes[key] = box

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        add = buttons.addButton("➕ Add to batch", QDialogButtonBox.AcceptRole)
        add.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update()

    def keys(self) -> tuple[str, ...]:
        return tuple(k for k, box in self.boxes.items() if box.isEnabled() and box.isChecked())

    def _update(self) -> None:
        name = batch.render_name(self.pattern, self.job) + batch.addition(self.job, self.keys())
        self.preview.setText(f"File name: <b>{output_path(self.job, self.folder, name).name}</b>")

    def accept(self) -> None:
        # remember the choice of every applicable box, keep the others as they were
        chosen = _stored()
        for key, box in self.boxes.items():
            if box.isEnabled():
                (chosen.add if box.isChecked() else chosen.discard)(key)
        QSettings().setValue(_KEY, ",".join(sorted(chosen)))
        super().accept()
