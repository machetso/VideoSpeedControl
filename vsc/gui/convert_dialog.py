# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""'Convert videos' window: re-encode many files (or whole folders) with one codec and quality,
keeping length, frame rate, size and sound (`core/convert.py`). Independent of the clip list
and the slow-motion settings of the main window.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QProgressBar, QPushButton, QRadioButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import batch, convert, formats
from ..core.probe import probe, scan_frames
from .clips import fmt_bytes, fmt_seconds
from .settings_panel import Combo
from . import workers

COLUMNS = ("File", "Length", "Size", "Status")
_FILE, _LENGTH, _SIZE, _STATUS = range(4)


class _ProbeSignals(QObject):
    done = Signal(object, object, object)    # path, MediaInfo, FrameMap
    failed = Signal(object, str)             # path, message


class _Probe(QRunnable):
    def __init__(self, path: Path, signals: _ProbeSignals):
        super().__init__()
        self.path, self.signals = path, signals

    def run(self) -> None:
        try:
            info = probe(self.path)
            frames = scan_frames(self.path, info.stream_index)
            if frames.count == 0:
                raise ValueError("no video frames")
            workers._emit(self.signals.done, self.path, info, frames)
        except Exception as e:      # noqa: BLE001 – any failure: the file can't be converted
            msg = str(e).strip().splitlines()[-1] if str(e).strip() else type(e).__name__
            workers._emit(self.signals.failed, self.path, msg)


class _Row:
    def __init__(self, path: Path):
        self.path = path
        self.info = None
        self.frames = None
        self.error = ""
        self.status = "Reading…"
        self.output: Path | None = None      # converted file (not converted again)

    @property
    def todo(self) -> bool:
        return self.info is not None and not (self.output and self.output.exists())


class ConvertDialog(QDialog):
    """`encoders()` returns the main window's encoder status (None while it is detected)."""

    def __init__(self, parent=None, encoders=lambda: None):
        super().__init__(parent)
        self.setWindowTitle("Convert videos")
        self.setAcceptDrops(True)
        self.resize(760, 560)
        self._encoders = encoders
        self.rows: list[_Row] = []
        self._batch: batch.Batch | None = None
        self._items: list[batch.Item] = []
        self._row_of_item: list[int] = []
        self._frames_before: list[int] = []
        self._start = 0.0
        self._probe_signals = _ProbeSignals(self)
        self._probe_signals.done.connect(self._probed)
        self._probe_signals.failed.connect(self._probe_failed)
        self._batch_signals = workers.BatchSignals(self)
        self._batch_signals.started.connect(self._item_started)
        self._batch_signals.progress.connect(self._item_progress)
        self._batch_signals.item_done.connect(self._item_done)
        self._batch_signals.finished.connect(self._finished)
        qs = QSettings()

        intro = QLabel("Re-encodes every video in the list with the same settings. Length, frame "
                       "rate, picture size and sound stay as they are; each video is saved as "
                       "MP4. Add files or whole folders – or drop them here.")
        intro.setWordWrap(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(_FILE, QHeaderView.Stretch)
        for c in (_LENGTH, _SIZE):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(_STATUS, QHeaderView.Interactive)
        self.table.setColumnWidth(_STATUS, 220)

        self.add_files_button = QPushButton("Add files…", clicked=self._add_files)
        self.add_folder_button = QPushButton("Add folder…", clicked=self._add_folder)
        self.remove_button = QPushButton("Remove", clicked=self._remove)
        self.clear_button = QPushButton("Clear list", clicked=self._clear)
        self.subfolders = QCheckBox("Include sub-folders")
        self.subfolders.setChecked(qs.value("convert/subfolders", True, type=bool))
        self.subfolders.toggled.connect(lambda v: QSettings().setValue("convert/subfolders", v))
        list_row = QHBoxLayout()
        for w in (self.add_files_button, self.add_folder_button, self.remove_button,
                  self.clear_button):
            list_row.addWidget(w)
        list_row.addStretch(1)
        list_row.addWidget(self.subfolders)

        # settings
        self.codec_combo = Combo()
        self.codec_combo.setToolTip("Video codec of the converted files (all MP4).")
        self.quality_combo = Combo()
        self.sound = QCheckBox("Keep the sound")
        self.sound.setChecked(qs.value("convert/sound", True, type=bool))
        self.sound.toggled.connect(lambda v: QSettings().setValue("convert/sound", v))
        self.next_to = QRadioButton(f"A “{convert.FOLDER_NAME}” folder next to each original")
        self.chosen = QRadioButton("This folder:")
        group = QButtonGroup(self)
        group.addButton(self.next_to)
        group.addButton(self.chosen)
        self.folder_edit = QLineEdit(qs.value("convert/folder", "", type=str))
        self.folder_edit.setPlaceholderText("Choose a folder…")
        self.folder_edit.textChanged.connect(self._folder_changed)
        browse = QPushButton("Choose…", clicked=self._choose_folder)
        (self.chosen if qs.value("convert/use_folder", False, type=bool) and self.folder_edit.text()
         else self.next_to).setChecked(True)
        self.chosen.toggled.connect(self._refresh)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.chosen)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        form = QFormLayout()
        form.addRow("Codec:", self.codec_combo)
        form.addRow("Quality:", self.quality_combo)
        form.addRow("", self.sound)
        form.addRow("Save to:", self.next_to)
        form.addRow("", _wrap(folder_row))
        note = QLabel("Existing files are never overwritten: a number is added (name_2 …).")
        note.setStyleSheet("color: gray")
        form.addRow("", note)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.start_button = QPushButton("Convert", clicked=self._start_or_cancel)
        self.start_button.setDefault(True)
        close = QPushButton("Close", clicked=self.close)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(close)
        bottom.addWidget(self.start_button)

        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addWidget(self.table, 1)
        lay.addLayout(list_row)
        lay.addLayout(form)
        lay.addWidget(self.progress)
        lay.addLayout(bottom)

        self.codec_combo.currentIndexChanged.connect(self._codec_changed)
        self.quality_combo.currentIndexChanged.connect(
            lambda: QSettings().setValue("convert/level", self.quality_combo.currentIndex()))
        self.refresh_codecs()

    # ------------------------------------------------------------------ settings

    def refresh_codecs(self) -> None:
        """Fill the codec list (again when the encoder detection has finished)."""
        status = self._encoders()
        wanted = self.codec_combo.currentData() or QSettings().value(
            "convert/codec", convert.DEFAULT_CODEC, type=str)
        self.codec_combo.blockSignals(True)
        self.codec_combo.clear()
        first_ok = None
        for key in convert.CODECS:
            codec = formats.CODECS_BY_KEY[key]
            st = status.get(key) if status else None
            ok = st is None or st.available
            self.codec_combo.addItem(codec.label if ok else f"{codec.label} – not available", key)
            if not ok:
                self.codec_combo.model().item(self.codec_combo.count() - 1).setEnabled(False)
            elif first_ok is None:
                first_ok = key
        pick = wanted if wanted in convert.CODECS and (
            not status or (status.get(wanted) is None or status[wanted].available)) else first_ok
        self.codec_combo.setCurrentIndex(max(0, self.codec_combo.findData(pick)))
        self.codec_combo.blockSignals(False)
        self._codec_changed()

    def _codec_changed(self) -> None:
        key = self.codec_combo.currentData()
        if key:
            QSettings().setValue("convert/codec", key)
        codec = formats.CODECS_BY_KEY.get(key)
        level = self.quality_combo.currentIndex()
        if level < 0:
            level = QSettings().value("convert/level", convert.DEFAULT_LEVEL, type=int)
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        for name, tip, _ in (formats.quality_levels(codec) if codec else []):
            self.quality_combo.addItem(name, None)
            self.quality_combo.setItemData(self.quality_combo.count() - 1, tip, Qt.ToolTipRole)
        self.quality_combo.setCurrentIndex(min(max(level, 0), self.quality_combo.count() - 1))
        self.quality_combo.blockSignals(False)
        self._refresh()

    def _folder_changed(self, text: str) -> None:
        QSettings().setValue("convert/folder", text)
        if text and not self.chosen.isChecked():
            self.chosen.setChecked(True)
        self._refresh()

    def _choose_folder(self) -> None:
        start = self.folder_edit.text() or (str(self.rows[0].path.parent) if self.rows else "")
        folder = QFileDialog.getExistingDirectory(self, "Save converted videos in", start)
        if folder:
            self.folder_edit.setText(folder)
            self.chosen.setChecked(True)

    def output_folder(self) -> Path | None:
        """None = the 'Converted' folder next to each original."""
        if self.chosen.isChecked() and self.folder_edit.text().strip():
            return Path(self.folder_edit.text().strip()).expanduser()
        return None

    # ------------------------------------------------------------------ the list

    def add_paths(self, paths) -> int:
        """Add files and the videos inside folders; returns how many were new."""
        known = {r.path.resolve() for r in self.rows}
        new = 0
        for path in convert.find_videos(paths, self.subfolders.isChecked()):
            if path.resolve() in known:
                continue
            known.add(path.resolve())
            row = _Row(path)
            self.rows.append(row)
            self._append_row(row)
            workers.start(_Probe(path, self._probe_signals))
            new += 1
        self._refresh()
        return new

    def _add_files(self) -> None:
        from .main_window import VIDEO_FILTER
        files, _ = QFileDialog.getOpenFileNames(self, "Add videos", "", VIDEO_FILTER)
        self.add_paths([Path(f) for f in files])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add all videos in a folder")
        if folder and not self.add_paths([Path(folder)]):
            QMessageBox.information(self, "Convert videos", "No (new) videos found in this folder.")

    def _append_row(self, row: _Row) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        item = QTableWidgetItem(row.path.name)
        item.setToolTip(str(row.path))
        self.table.setItem(r, _FILE, item)
        for c in (_LENGTH, _SIZE, _STATUS):
            self.table.setItem(r, c, QTableWidgetItem(""))
        self._show(r)

    def _show(self, r: int) -> None:
        row = self.rows[r]
        info = row.info
        self.table.item(r, _LENGTH).setText(fmt_seconds(info.duration) if info else "")
        self.table.item(r, _SIZE).setText(fmt_bytes(info.size_bytes) if info else "")
        status = self.table.item(r, _STATUS)
        status.setText(row.status)
        status.setToolTip(row.error or (f"{info.codec} {info.width}×{info.height} "
                                        f"{float(info.fps):.5g} fps" if info else ""))

    def _index(self, path: Path) -> int | None:
        return next((i for i, r in enumerate(self.rows) if r.path == path), None)

    def _probed(self, path, info, frames) -> None:
        i = self._index(path)
        if i is None:
            return
        row = self.rows[i]
        row.info, row.frames = info, frames
        row.status = f"Ready – {info.codec} {info.width}×{info.height}, {float(info.fps):.4g} fps"
        self._show(i)
        self._refresh()

    def _probe_failed(self, path, message: str) -> None:
        i = self._index(path)
        if i is None:
            return
        self.rows[i].error = message
        self.rows[i].status = "Cannot be read"
        self._show(i)
        self._refresh()

    def _remove(self) -> None:
        for r in sorted({i.row() for i in self.table.selectionModel().selectedRows()},
                        reverse=True):
            self.table.removeRow(r)
            del self.rows[r]
        self._refresh()

    def _clear(self) -> None:
        self.table.setRowCount(0)
        self.rows.clear()
        self._refresh()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and not self._batch:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.add_paths([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()

    # ------------------------------------------------------------------ converting

    def _ready_rows(self) -> list[int]:
        return [i for i, r in enumerate(self.rows) if r.todo]

    def _refresh(self, *_) -> None:
        if self._batch:
            return
        ready = self._ready_rows()
        reading = sum(r.info is None and not r.error for r in self.rows)
        failed = sum(r.info is None and bool(r.error) for r in self.rows)
        missing_folder = self.chosen.isChecked() and not self.folder_edit.text().strip()
        converted = sum(r.info is not None and not r.todo for r in self.rows)
        parts = [f"{len(ready)} video{'s' * (len(ready) != 1)} to convert"]
        if ready:
            parts[0] += f" ({fmt_seconds(sum(self.rows[i].info.duration for i in ready))})"
        if converted:
            parts.append(f"{converted} already converted")
        if reading:
            parts.append(f"{reading} still being read")
        if failed:
            parts.append(f"{failed} cannot be read")
        if missing_folder:
            parts.append("choose the folder to save to")
        self.summary.setText(", ".join(parts) if self.rows else "Add videos to convert.")
        self.start_button.setText(f"Convert {len(ready)}" if ready else "Convert")
        self.start_button.setEnabled(bool(ready) and not reading and not missing_folder
                                     and self.codec_combo.currentData() is not None)

    def _jobs(self) -> list[tuple]:
        key = self.codec_combo.currentData()
        level = self.quality_combo.currentIndex()
        status = self._encoders()
        pix = (status[key].pix_fmts or None) if status and key in status else None
        jobs = []
        for i in self._ready_rows():
            r = self.rows[i]
            jobs.append((convert.make_job(r.info, r.frames, key, level, self.sound.isChecked()), pix))
        return jobs

    def _start_or_cancel(self) -> None:
        if self._batch:
            self._batch.cancel()
            self.start_button.setEnabled(False)
            return
        rows = self._ready_rows()
        items = convert.plan(self._jobs(), self.output_folder())
        try:
            for folder in {it.output.parent for it in items if it.output}:
                folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Convert videos", f"Cannot create the output folder:\n{e}")
            return
        QSettings().setValue("convert/use_folder", self.chosen.isChecked())
        self._items, self._row_of_item = items, rows
        frames = [it.job.output_frame_count if it.output else 0 for it in items]
        self._frames_before = [sum(frames[:k]) for k in range(len(frames))]
        self._total_frames = max(1, sum(frames))
        for k, i in enumerate(rows):
            self.rows[i].status = "Waiting" if items[k].output else items[k].note
            self._show(i)
        self._batch = batch.Batch(items)
        self._start = time.monotonic()
        self._set_running(True)
        workers.start(workers.BatchTask(self._batch, self._batch_signals))

    def _set_running(self, running: bool) -> None:
        for w in (self.add_files_button, self.add_folder_button, self.remove_button,
                  self.clear_button, self.codec_combo, self.quality_combo, self.sound,
                  self.next_to, self.chosen, self.folder_edit, self.subfolders):
            w.setEnabled(not running)
        self.start_button.setText("Cancel" if running else "Convert")
        self.start_button.setEnabled(True)
        if not running:
            self._refresh()

    def _item_started(self, k: int) -> None:
        i = self._row_of_item[k]
        self.rows[i].status = "Converting…"
        self._show(i)
        self.table.scrollToItem(self.table.item(i, _FILE))

    def _item_progress(self, k: int, p) -> None:
        i = self._row_of_item[k]
        eta = f", {fmt_seconds(p.eta)} left" if p.eta is not None else ""
        self.rows[i].status = f"Converting… {p.fraction * 100:.0f} %{eta}"
        self.table.item(i, _STATUS).setText(self.rows[i].status)
        done = self._frames_before[k] + p.frame
        self.progress.setValue(int(1000 * done / self._total_frames))
        elapsed = time.monotonic() - self._start
        left = elapsed * (self._total_frames - done) / done if done else None
        self.summary.setText(f"Video {k + 1} of {len(self._items)}"
                             + (f" – about {fmt_seconds(left)} left in total" if left else ""))

    def _item_done(self, r: batch.ItemResult) -> None:
        i = self._row_of_item[r.index]
        row = self.rows[i]
        if r.status == "done":
            row.status, row.error, row.output = f"✔ {r.output.name}", str(r.output), r.output
        elif r.status == "failed":
            row.status, row.error = "Failed", r.error
        elif r.status == "cancelled":
            row.status = "Cancelled"
        else:
            row.status = r.error or "Skipped"
        self._show(i)

    def _finished(self, result: batch.BatchResult) -> None:
        self._batch = None
        self.progress.setValue(1000 if not result.cancelled else self.progress.value())
        self._set_running(False)
        done, failed = result.count("done"), result.count("failed")
        text = f"{done} converted"
        if failed:
            text += f", {failed} failed (see the Status column)"
        if result.cancelled:
            text += ", cancelled"
        self.summary.setText(text + f" in {fmt_seconds(time.monotonic() - self._start)}.")

    def closeEvent(self, event) -> None:
        if self._batch:
            if QMessageBox.question(self, "Convert videos",
                                    "A conversion is running. Cancel it and close?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self._batch.cancel()
        super().closeEvent(event)


def _wrap(layout) -> QWidget:
    w = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    w.setLayout(layout)
    return w
