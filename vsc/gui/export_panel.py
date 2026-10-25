"""Export: output folder, file name pattern, overwrite policy and the queue with progress."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QRadioButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import batch
from .clips import fmt_seconds

STATUS_TEXT = {"queued": "Queued", "running": "Encoding…", "done": "Done", "failed": "Failed",
               "cancelled": "Cancelled", "skipped": "Skipped"}
STATUS_COLOR = {"done": "#27ae60", "failed": "#c0392b", "cancelled": "#d35400",
                "skipped": "#7f8c8d"}


class ExportPanel(QWidget):
    start = Signal()
    cancel = Signal()
    options_changed = Signal()

    def __init__(self, settings: QSettings | None = None, parent=None):
        super().__init__(parent)
        self.store = settings or QSettings()
        self.running = False
        self._outputs: list[Path | None] = []

        self.next_to_source = QRadioButton("Next to each source file")
        self.to_folder = QRadioButton("Folder:")
        group = QButtonGroup(self)
        group.addButton(self.next_to_source)
        group.addButton(self.to_folder)
        self.folder = QLineEdit(self.store.value("export/folder", str(Path.home() / "Videos")))
        browse = QPushButton("Browse…")
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
        tokens = "\n".join(f"{t}  –  {d}" for t, d in batch.PATTERN_TOKENS.items())
        self.pattern.setToolTip("File name without extension. Placeholders:\n" + tokens)
        self.pattern.setPlaceholderText(batch.DEFAULT_PATTERN)
        pattern_help = QLabel("Placeholders: " + "  ".join(batch.PATTERN_TOKENS))
        pattern_help.setStyleSheet("color: gray")
        pattern_help.setToolTip(tokens)

        self.policy = QComboBox()
        for key, label in batch.POLICIES:
            self.policy.addItem(label, key)
        idx = self.policy.findData(self.store.value("export/policy", batch.RENAME))
        self.policy.setCurrentIndex(max(0, idx))

        self.scope = QComboBox()
        self.scope.addItem("All clips", "all")
        self.scope.addItem("Selected clips only", "selected")

        form = QFormLayout()
        form.addRow("Save to", self.next_to_source)
        form.addRow("", folder_row)
        form.addRow("File name", self.pattern)
        form.addRow("", pattern_help)
        form.addRow("If the file exists", self.policy)
        form.addRow("Export", self.scope)

        self.queue = QTreeWidget()
        self.queue.setColumnCount(3)
        self.queue.setHeaderLabels(["Clip", "Output file", "Status"])
        self.queue.setRootIsDecorated(False)
        self.queue.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.queue.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.start_button = QPushButton("Start export")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton("Open output folder")
        self.open_button.clicked.connect(self._open_folder)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)

        self.clip_progress = QProgressBar()
        self.overall = QProgressBar()
        self.overall.setFormat("%p % of the batch")
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

    def _changed(self) -> None:
        self.folder.setEnabled(self.to_folder.isChecked())
        self.store.setValue("export/folder", self.folder.text())
        self.store.setValue("export/next_to_source",
                            "true" if self.next_to_source.isChecked() else "false")
        self.store.setValue("export/pattern", self.pattern.text())
        self.store.setValue("export/policy", self.policy_key())
        self.options_changed.emit()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder", self.folder.text())
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
            row = QTreeWidgetItem([name, self._out_text(item.output), item.note])
            if item.output is None:
                row.setForeground(2, QColor(STATUS_COLOR["skipped"]))
            elif item.note.startswith("overwrites"):
                row.setForeground(2, QColor(STATUS_COLOR["cancelled"]))
            row.setToolTip(1, str(item.output or ""))
            self.queue.addTopLevelItem(row)
            self._outputs.append(item.output)
        runnable = sum(it.output is not None for it in items)
        self.start_button.setEnabled(runnable > 0)
        text = f"{runnable} clip(s) will be exported." if items else "No clips to export."
        if problems:
            text += "  Not included: " + "; ".join(problems)
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
        if not running:
            self.folder.setEnabled(self.to_folder.isChecked())
        else:
            for i in range(self.queue.topLevelItemCount()):
                if self._outputs[i] is not None:
                    self.set_status(i, "queued")
            self._reset_progress()

    def set_status(self, index: int, status: str, detail: str = "") -> None:
        row = self.queue.topLevelItem(index)
        if row is None:
            return
        row.setText(2, STATUS_TEXT.get(status, status) + (f" – {detail}" if detail else ""))
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
        self.clip_progress.setFormat("Current clip")
        self.overall.setRange(0, 1000)
        self.overall.setValue(0)

    def set_progress(self, clip_name: str, clip_fraction: float, clip_text: str,
                     overall_fraction: float, overall_text: str) -> None:
        self.clip_progress.setValue(round(clip_fraction * 1000))
        self.clip_progress.setFormat(f"{clip_name}: {clip_fraction:.0%}  {clip_text}")
        self.overall.setValue(round(overall_fraction * 1000))
        self.overall.setFormat(f"Batch: {overall_fraction:.0%}  {overall_text}")

    def finished(self, result: batch.BatchResult, elapsed: float) -> None:
        self.set_running(False)
        parts = [f"{result.count('done')} done"]
        for status in ("failed", "skipped", "cancelled"):
            if result.count(status):
                parts.append(f"{result.count(status)} {status}")
        text = ("Export cancelled: " if result.cancelled else "Export finished: ") + ", ".join(parts)
        text += f" in {fmt_seconds(elapsed)}."
        if result.count("failed"):
            text += "  Hover over “Failed” for the error message."
        if result.count("cancelled") or result.count("failed"):
            text += "  Incomplete files were deleted."
        self.message.setText(text)
        if not result.cancelled:
            self.overall.setValue(1000)
            self.overall.setFormat("Batch: done")
