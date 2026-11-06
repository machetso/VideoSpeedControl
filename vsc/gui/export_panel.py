# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Export: output folder, file name pattern, overwrite policy and the queue with progress."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QRadioButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import batch
from ..i18n import N_, tr, trp
from .clips import fmt_seconds

STATUS_TEXT = {"queued": N_("Queued"), "running": N_("Encoding…"), "done": N_("Done"),
               "failed": N_("Failed"), "cancelled": N_("Cancelled"), "skipped": N_("Skipped")}
OVERWRITES = "overwrites the existing file"     # batch.plan's note (compared untranslated)
STATUS_COLOR = {"done": "#27ae60", "failed": "#c0392b", "cancelled": "#d35400",
                "skipped": "#7f8c8d"}


class ExportPanel(QWidget):
    start = Signal()
    cancel = Signal()
    options_changed = Signal()
    remove_entries = Signal(list)    # rows of the batch list to remove
    clear_entries = Signal()
    open_entry = Signal(int)         # row of the batch list double-clicked

    def __init__(self, settings: QSettings | None = None, parent=None):
        super().__init__(parent)
        self.store = settings or QSettings()
        self.running = False
        self._outputs: list[Path | None] = []
        self._done_rows: set[int] = set()

        self.next_to_source = QRadioButton(tr("Next to each source file"))
        self.to_folder = QRadioButton(tr("Folder:"))
        group = QButtonGroup(self)
        group.addButton(self.next_to_source)
        group.addButton(self.to_folder)
        self.folder = QLineEdit(self.store.value("export/folder", str(Path.home() / "Videos")))
        browse = QPushButton(tr("Browse…"))
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.to_folder)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        if self.store.value("export/next_to_source", "false") == "true":
            self.next_to_source.setChecked(True)
        else:
            self.to_folder.setChecked(True)

        self.pattern = QLineEdit(self.store.value("export/pattern", batch.DEFAULT_PATTERN))
        tokens = "\n".join(f"{t}  –  {tr(d)}" for t, d in batch.PATTERN_TOKENS.items())
        self.pattern.setToolTip(tr("File name without extension. Placeholders:") + "\n" + tokens)
        self.pattern.setPlaceholderText(batch.DEFAULT_PATTERN)
        pattern_help = QLabel(tr("Placeholders: %s", "  ".join(batch.PATTERN_TOKENS)))
        pattern_help.setStyleSheet("color: gray")
        pattern_help.setToolTip(tokens)

        self.policy = QComboBox()
        for key, label in batch.POLICIES:
            self.policy.addItem(tr(label), key)
        idx = self.policy.findData(self.store.value("export/policy", batch.RENAME))
        self.policy.setCurrentIndex(max(0, idx))

        self.scope = QComboBox()
        self.scope.addItem(tr("All clips"), "all")
        self.scope.addItem(tr("Selected clips only"), "selected")
        self.scope.addItem(tr("Batch list (added in Preview & trim)"), "batch")
        self.scope.setItemData(2, tr("Snapshots added with “Add to batch” – the same clip can be "
                                     "in the list several times, e.g. lossless and smart."),
                               Qt.ToolTipRole)
        self.remove_button = QPushButton(tr("Remove from list"))
        self.remove_button.setToolTip(tr("Remove the selected entries from the batch list"))
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button = QPushButton(tr("Clear list"))
        self.clear_button.clicked.connect(self.clear_entries)
        scope_row = QHBoxLayout()
        scope_row.addWidget(self.scope, 1)
        scope_row.addWidget(self.remove_button)
        scope_row.addWidget(self.clear_button)

        form = QFormLayout()
        form.addRow(tr("Save to"), self.next_to_source)
        form.addRow("", folder_row)
        form.addRow(tr("File name"), self.pattern)
        form.addRow("", pattern_help)
        form.addRow(tr("If the file exists"), self.policy)
        form.addRow(tr("Export"), scope_row)

        self.queue = QTreeWidget()
        self.queue.setColumnCount(3)
        self.queue.setHeaderLabels([tr("Clip"), tr("Output file"), tr("Status")])
        self.queue.setRootIsDecorated(False)
        self.queue.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.queue.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.queue.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.queue.itemDoubleClicked.connect(self._double_clicked)

        self.start_button = QPushButton(tr("Start export"))
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton(tr("Open output folder"))
        self.open_button.clicked.connect(self._open_folder)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)

        self.clip_progress = QProgressBar()
        self.overall = QProgressBar()
        self.overall.setFormat(tr("%s %% of the batch", "%p"))
        self.message = QLabel()
        self.message.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.queue, 1)
        layout.addWidget(self.clip_progress)
        layout.addWidget(self.overall)
        layout.addWidget(self.message)
        layout.addLayout(buttons)
        self._reset_progress()

        for w in (self.folder, self.pattern):
            w.textChanged.connect(self._changed)
        for w in (self.policy, self.scope):
            w.currentIndexChanged.connect(self._changed)
        self.next_to_source.toggled.connect(self._changed)

    # ------------------------------------------------------------------ options

    def output_folder(self) -> Path | None:
        if self.next_to_source.isChecked():
            return None
        return Path(self.folder.text().strip()).expanduser()

    def pattern_text(self) -> str:
        return self.pattern.text().strip() or batch.DEFAULT_PATTERN

    def policy_key(self) -> str:
        return self.policy.currentData()

    def selected_only(self) -> bool:
        return self.scope.currentData() == "selected"

    def batch_list(self) -> bool:
        return self.scope.currentData() == "batch"

    def show_batch_list(self) -> None:
        self.scope.setCurrentIndex(self.scope.findData("batch"))

    def _remove_selected(self) -> None:
        rows = sorted({self.queue.indexOfTopLevelItem(i) for i in self.queue.selectedItems()})
        if rows:
            self.remove_entries.emit(rows)

    def _double_clicked(self, item) -> None:
        if self.batch_list() and not self.running:
            self.open_entry.emit(self.queue.indexOfTopLevelItem(item))

    def _update_list_buttons(self) -> None:
        on = self.batch_list() and not self.running
        self.remove_button.setVisible(self.batch_list())
        self.clear_button.setVisible(self.batch_list())
        self.remove_button.setEnabled(on and self.queue.topLevelItemCount() > 0)
        self.clear_button.setEnabled(on and self.queue.topLevelItemCount() > 0)

    def _changed(self) -> None:
        self.folder.setEnabled(self.to_folder.isChecked())
        self.store.setValue("export/folder", self.folder.text())
        self.store.setValue("export/next_to_source",
                            "true" if self.next_to_source.isChecked() else "false")
        self.store.setValue("export/pattern", self.pattern.text())
        self.store.setValue("export/policy", self.policy_key())
        self.options_changed.emit()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Output folder"), self.folder.text())
        if folder:
            self.folder.setText(folder)
            self.to_folder.setChecked(True)

    def _open_folder(self) -> None:
        folder = self.output_folder()
        if folder is None:
            done = [p for p in self._outputs if p]
            folder = done[0].parent if done else None
        if folder and folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------------ queue

    def show_plan(self, names: list[str], items: list[batch.Item], problems: list[str]) -> None:
        """The planned outputs (before the export starts)."""
        if self.running:
            return
        self.queue.clear()
        self._outputs = []
        for name, item in zip(names, items):
            row = QTreeWidgetItem([name, self._out_text(item.output), tr(item.note)])
            if item.done:
                row.setText(2, tr("Done – exported earlier, not exported again"))
                row.setForeground(2, QColor(STATUS_COLOR["done"]))
            elif item.output is None:
                row.setForeground(2, QColor(STATUS_COLOR["skipped"]))
            elif item.kind == "overwrite":                # language-independent (batch.Item.kind)
                row.setForeground(2, QColor(STATUS_COLOR["cancelled"]))
            row.setToolTip(1, str(item.output or ""))
            if self.batch_list():
                row.setToolTip(0, tr("Double-click: open this entry in Preview & trim – edit it "
                                     "or add another encoding of the clip"))
            self.queue.addTopLevelItem(row)
            self._outputs.append(item.output)
        runnable = sum(it.output is not None and not it.done for it in items)
        done = sum(it.done for it in items)
        self._done_rows = {i for i, it in enumerate(items) if it.done}
        self.start_button.setEnabled(runnable > 0)
        self._update_list_buttons()
        text = trp("%d clip(s) will be exported.", "%d clip(s) will be exported.", runnable,
                   runnable) if items else tr("No clips to export.")
        if done:
            text += "  " + trp("%d already exported (kept in the list, not exported again – "
                               "edit an entry or delete its file to export it again).",
                               "%d already exported (kept in the list, not exported again – "
                               "edit an entry or delete its file to export it again).",
                               done, done)
        if problems:
            text += "  " + tr("Not included: %s", "; ".join(tr(p) for p in problems))
        self.message.setText(text)

    @staticmethod
    def _out_text(path: Path | None) -> str:
        if path is None:
            return "–"
        return f"{path.parent.name}/{path.name}" if "%" in path.name else path.name

    def set_running(self, running: bool) -> None:
        self.running = running
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        for w in (self.next_to_source, self.to_folder, self.folder, self.pattern, self.policy,
                  self.scope):
            w.setEnabled(not running)
        self._update_list_buttons()
        if not running:
            self.folder.setEnabled(self.to_folder.isChecked())
        else:
            for i in range(self.queue.topLevelItemCount()):
                if self._outputs[i] is not None and i not in self._done_rows:
                    self.set_status(i, "queued")
            self._reset_progress()

    def set_status(self, index: int, status: str, detail: str = "") -> None:
        row = self.queue.topLevelItem(index)
        if row is None:
            return
        row.setText(2, tr(STATUS_TEXT.get(status, status)) + (f" – {tr(detail)}" if detail else ""))
        row.setForeground(2, QColor(STATUS_COLOR.get(status, self.palette().text().color())))
        if status == "running":
            self.queue.scrollToItem(row)

    def set_error(self, index: int, error: str) -> None:
        row = self.queue.topLevelItem(index)
        if row is not None and error:
            row.setToolTip(2, error)

    def _reset_progress(self) -> None:
        self.clip_progress.setRange(0, 1000)
        self.clip_progress.setValue(0)
        self.clip_progress.setFormat(tr("Current clip"))
        self.overall.setRange(0, 1000)
        self.overall.setValue(0)

    def set_progress(self, clip_name: str, clip_fraction: float, clip_text: str,
                     overall_fraction: float, overall_text: str) -> None:
        self.clip_progress.setValue(round(clip_fraction * 1000))
        self.clip_progress.setFormat(f"{clip_name}: {clip_fraction:.0%}  {clip_text}")
        self.overall.setValue(round(overall_fraction * 1000))
        self.overall.setFormat(tr("Batch: %s  %s", f"{overall_fraction:.0%}", overall_text))

    def finished(self, result: batch.BatchResult, elapsed: float) -> None:
        self.set_running(False)
        n = result.count("done")
        parts = [trp("%d done", "%d done", n, n)]
        n = result.count("failed")
        if n:
            parts.append(trp("%d failed", "%d failed", n, n))
        n = result.count("skipped")
        if n:
            parts.append(trp("%d skipped", "%d skipped", n, n))
        n = result.count("cancelled")
        if n:
            parts.append(trp("%d cancelled", "%d cancelled", n, n))
        text = (tr("Export cancelled: %s in %s.", ", ".join(parts), fmt_seconds(elapsed))
                if result.cancelled else
                tr("Export finished: %s in %s.", ", ".join(parts), fmt_seconds(elapsed)))
        if result.count("failed"):
            text += "  " + tr("Hover over “Failed” for the error message.")
        if result.count("cancelled") or result.count("failed"):
            text += "  " + tr("Incomplete files were deleted.")
        self.message.setText(text)
        if not result.cancelled:
            self.overall.setValue(1000)
            self.overall.setFormat(tr("Batch: done"))
