# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Main window: clip table on top; below, preview / clip info tabs next to the output settings."""
from __future__ import annotations

import copy
from dataclasses import dataclass
import time
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMainWindow,
                               QMenu, QMessageBox, QSizePolicy, QSplitter, QTableView, QTabWidget,
                               QToolBar, QToolButton, QWidget)

from ..core import batch, testencode, treatment
from ..core.command import CommandError
from ..core.formats import CODECS_BY_KEY
from ..core.job import Job
from .clips import Clip, ClipModel, Status, fmt_bytes, fmt_seconds
from .export_panel import ExportPanel
from .info_panel import InfoPanel
from .settings_panel import SettingsPanel
from .test_panel import TestPanel
from .batch_dialogs import EDIT, NEW, AdditionDialog, ask_entry_action
from .timeline import PreviewPanel
from . import help, workers

VIDEO_FILTER = ("Video files (*.mp4 *.mov *.mkv *.avi *.mts *.m2ts *.mxf *.webm *.m4v *.wmv "
                "*.flv *.360 *.lrv *.MP4 *.MOV *.MKV *.AVI *.MTS);;"
                "Clip Speed Treatments (*.cst);;All files (*)")
CST_FILTER = "Clip Speed Treatments (*.cst);;All files (*)"


@dataclass
class BatchEntry:
    clip: Clip
    job: Job                     # snapshot taken by "Add to batch"
    label: str
    pix_fmts: list[str] | None
    ui: dict                     # widget choices of the snapshot (to open it again)
    additions: tuple[str, ...] = ()   # name additions (batch.ADDITIONS keys)
    exported: Path | None = None      # output of a successful export – not exported again

    @property
    def done(self) -> bool:
        """Exported, and the file is still there (deleted → it is exported again)."""
        return self.exported is not None and self.exported.exists()


def _snapshot(job: Job) -> Job:
    """An independent copy: later edits of the clip do not change it."""
    return Job(job.info, job.settings.clone(), copy.copy(job.trim), job.frames,
               list(job.segments), job.joins)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoSpeedControl")
        self.resize(1300, 850)
        self.setAcceptDrops(True)

        self.model = ClipModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.selectionModel().currentRowChanged.connect(self._current_changed)

        self.info = InfoPanel()
        self.preview = PreviewPanel()
        self.preview.trim_changed.connect(self._trim_changed)
        self.preview.add_to_batch.connect(self.add_to_batch)
        self.preview.update_entry.connect(self._update_entry)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.preview, "Preview && trim")
        self.test_panel = TestPanel()
        self.test_panel.start_test.connect(self._start_test)
        self.test_panel.cancel_test.connect(self._cancel_test)
        self.tabs.addTab(self.test_panel, "Test encode")
        self.tabs.addTab(self.info, "Clip info")
        self.export_panel = ExportPanel()
        self.export_panel.start.connect(self.start_export)
        self.export_panel.cancel.connect(self._cancel_export)
        self.export_panel.options_changed.connect(self._plan_export)
        self.export_panel.remove_entries.connect(self._remove_entries)
        self.export_panel.clear_entries.connect(lambda: self._remove_entries(
            list(range(len(self.batch_entries)))))
        self.export_panel.open_entry.connect(self._open_entry)
        self.batch_entries: list[BatchEntry] = []     # snapshots from "Add to batch"
        self._editing: BatchEntry | None = None       # entry opened with "Edit this entry"
        self._pending: dict[Path, tuple[Path, treatment.Treatment]] = {}   # clip → (.cst, data)
        self.tabs.addTab(self.export_panel, "Export")
        self._batch: batch.Batch | None = None
        self._batch_clips: list[Clip] = []
        self._batch_entries: list[BatchEntry] | None = None   # batch list run: item → entry
        self._batch_estimates: list[float | None] = []
        self._batch_done_frames = 0
        self._batch_start = 0.0
        self.tabs.currentChanged.connect(lambda: self.test_panel.refresh())  # playhead may have moved
        self.tabs.currentChanged.connect(self._plan_export)   # files on disk may have changed
        self._tests: dict[int, testencode.TestEncode] = {}   # id(clip) → running test
        self.settings = SettingsPanel()
        self.settings.changed.connect(self._settings_changed)
        self.settings.apply_to_all.connect(self._apply_to_all)

        bottom = QSplitter(Qt.Horizontal)
        bottom.addWidget(self.tabs)
        bottom.addWidget(self.settings)
        bottom.setSizes([780, 520])
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(bottom)
        split.setSizes([170, 680])
        self.setCentralWidget(split)

        toolbar = QToolBar("Clips")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        add = QAction("Add files…", self, shortcut=QKeySequence.Open, triggered=self.add_dialog)
        remove = QAction("Remove", self, shortcut=QKeySequence.Delete, triggered=self.remove_selected)
        clear = QAction("Clear list", self, triggered=self.clear)
        self._list_actions = (remove, clear)    # disabled while an export runs
        for action in (add, remove, clear):
            toolbar.addAction(action)
        toolbar.addSeparator()
        load_cst = QAction("Load Clip Speed Treatment…", self, shortcut=QKeySequence("Ctrl+L"),
                           triggered=self.load_treatment_dialog)
        load_cst.setToolTip("Load a clip speed treatment (.cst): sections, trim and output "
                            "settings – only onto the video it was saved for (Ctrl+L)")
        save_cst = QAction("Save Clip Speed Treatment…", self, shortcut=QKeySequence.Save,
                           triggered=self.save_treatment)
        save_cst.setToolTip("Save the sections, trim and output settings of the current clip "
                            "as a clip speed treatment (.cst) (Ctrl+S)")
        for action in (load_cst, save_cst):
            toolbar.addAction(action)

        # Help: a button with a menu at the right end of the same row
        guide = QAction("User guide", self, shortcut=QKeySequence.HelpContents,
                        triggered=self.show_help)
        self.addAction(guide)                     # F1 works without opening the menu
        pdf = QAction("User guide (PDF)", self, triggered=self._open_pdf)
        pdf.setEnabled(help.PDF.is_file())
        menu = QMenu(self)
        menu.addAction(guide)
        menu.addAction(pdf)
        menu.addSeparator()
        menu.addAction(QAction("About VideoSpeedControl", self, triggered=self.show_about))
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        self.help_button = QToolButton()
        self.help_button.setText("Help")
        self.help_button.setToolTip("User guide (F1), PDF and About")
        self.help_button.setMenu(menu)
        self.help_button.setPopupMode(QToolButton.InstantPopup)
        toolbar.addWidget(self.help_button)
        self._help: help.HelpWindow | None = None

        self.batch_label = QLabel()
        self.statusBar().addPermanentWidget(self.batch_label)
        for sig in (self.model.dataChanged, self.model.rowsInserted, self.model.rowsRemoved):
            sig.connect(self._update_batch)
            sig.connect(self._plan_export)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.export_panel.selected_only() and self._plan_export())
        self.statusBar().showMessage("Detecting encoders…")
        self.clip_signals = workers.ClipSignals(self)
        self.clip_signals.probed.connect(self._probed)
        self.clip_signals.scanned.connect(self._scanned)
        self.clip_signals.analysed.connect(self._analysed)
        self.clip_signals.failed.connect(self._failed)
        self.thumb_signals = workers.ThumbnailSignals(self)
        self.thumb_signals.thumbnail.connect(self._thumbnail)
        self.proxy_signals = workers.ProxySignals(self)
        self.proxy_signals.progress.connect(lambda clip: self.preview.proxy_progress(clip))
        self.test_signals = workers.TestSignals(self)
        self.test_signals.progress.connect(self._test_progress)
        self.test_signals.done.connect(self._test_done)
        self.batch_signals = workers.BatchSignals(self)
        self.batch_signals.started.connect(self._export_started)
        self.batch_signals.progress.connect(self._export_progress)
        self.batch_signals.item_done.connect(self._export_item_done)
        self.batch_signals.finished.connect(self._export_finished)
        self.encoder_signals = workers.EncoderSignals(self)
        self.encoder_signals.done.connect(self._encoders_done)
        self.encoder_signals.failed.connect(
            lambda msg: self.statusBar().showMessage(f"Encoder detection failed: {msg}"))
        workers.start(workers.EncoderDetector(self.encoder_signals))

    def closeEvent(self, event) -> None:
        if self._batch:
            answer = QMessageBox.question(
                self, "Export running",
                "An export is still running. Cancel it and quit?\n"
                "The clip being encoded right now is deleted; finished clips are kept.")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._batch.cancel()
        for test in self._tests.values():
            test.cancel()
        for clip in self.model.clips:
            clip.removed = True          # stops thumbnail loaders
            testencode.discard(clip.test)
        super().closeEvent(event)

    # ------------------------------------------------------------------ import

    def show_help(self) -> None:
        if self._help is None:
            self._help = help.HelpWindow(self)
        self._help.show()
        self._help.raise_()
        self._help.activateWindow()

    def _open_pdf(self) -> None:
        if not help.open_pdf():
            self.statusBar().showMessage("The PDF user guide could not be opened", 5000)

    def show_about(self) -> None:
        help.AboutDialog(self).exec()

    def add_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add video files", "", VIDEO_FILTER)
        self.add_files([Path(f) for f in files])

    def add_files(self, paths: list[Path]) -> None:
        first_new = None
        for path in paths:
            if path.is_dir():
                continue
            if path.suffix.lower() == treatment.SUFFIX:
                self.open_treatment(path)
                continue
            clip = self.model.add(path.resolve())
            if clip:
                first_new = first_new or clip
                workers.start(workers.ClipLoader(clip.path, self.clip_signals))
        if first_new and not self.table.currentIndex().isValid():
            self._select(first_new)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        self.add_files(paths)
        event.acceptProposedAction()

    def remove_selected(self) -> None:
        rows = [i.row() for i in self.table.selectionModel().selectedRows()]
        self.model.remove_rows(rows)
        self._drop_removed_entries()
        self._current_changed(self.table.currentIndex())

    def clear(self) -> None:
        self.model.remove_rows(list(range(len(self.model.clips))))
        self._drop_removed_entries()
        self._current_changed(self.table.currentIndex())

    def _drop_removed_entries(self) -> None:
        self.batch_entries = [e for e in self.batch_entries if not e.clip.removed]
        self._plan_export()

    # ------------------------------------------------------------------ worker results

    def _clip(self, path: Path) -> Clip | None:
        return next((c for c in self.model.clips if c.path == path), None)

    def _probed(self, path, info) -> None:
        clip = self._clip(path)
        if clip:
            clip.info, clip.status = info, Status.SCANNING
            self._update(clip)

    def _scanned(self, path, frames) -> None:
        clip = self._clip(path)
        if clip:
            clip.frames, clip.status = frames, Status.READY
            clip.thumbs = [None] * workers.THUMB_COUNT
            workers.start(workers.ThumbnailLoader(clip, self.thumb_signals))
            workers.start(workers.ProxyLoader(clip, self.proxy_signals))
            self._update(clip)
            if path in self._pending:           # a .cst waited for this clip
                self._apply_treatment(clip, *self._pending.pop(path))

    def _analysed(self, path, joins) -> None:
        clip = self._clip(path)
        if clip:
            clip.joins = joins
            if clip.settings.smart:              # only smart output depends on the joins
                self.model.clip_changed(clip)
            if clip is self.current_clip():
                self.settings.refresh()          # enables the "Smart re-encode" option
                if clip.settings.smart:          # snapping points changed
                    self.preview.refresh()

    def _failed(self, path, message: str) -> None:
        clip = self._clip(path)
        if clip:
            clip.status, clip.error = Status.ERROR, message
            self._pending.pop(path, None)
            self._update(clip)

    def _thumbnail(self, clip: Clip, slot: int, index: int, image) -> None:
        if not clip.removed:
            clip.thumbs[slot] = (index, image)
            self.preview.thumbnail_arrived(clip)

    def _encoders_done(self, status, rife_status) -> None:
        n = sum(st.available for st in status.values())
        hw = [CODECS_BY_KEY[k].label for k, st in status.items()
              if st.available and CODECS_BY_KEY[k].hw]
        text = f"{n} encoders available" + (f", hardware: {', '.join(hw)}" if hw else
                                            ", no working hardware encoder (software only)")
        if rife_status.available:
            text += f" · RIFE on {rife_status.gpu}" + (" (software, slow)" if rife_status.software
                                                     else "")
        else:
            text += f" · RIFE unavailable: {rife_status.reason}"
        self.statusBar().showMessage(text)
        self.settings.set_encoders(status, rife_status)
        self._plan_export()

    # ------------------------------------------------------------------ selection / settings

    def current_clip(self) -> Clip | None:
        idx = self.table.currentIndex()
        return self.model.clips[idx.row()] if idx.isValid() else None

    def _select(self, clip: Clip) -> None:
        row = self.model.clips.index(clip)
        self.table.selectionModel().setCurrentIndex(
            self.model.index(row, 0),
            QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def _current_changed(self, *_) -> None:
        clip = self.current_clip()
        if self._editing and self._editing.clip is not clip:
            self._stop_editing()
        self.info.show_clip(clip)
        self.settings.set_clip(clip)
        self.preview.set_clip(clip)
        self.test_panel.set_clip(clip)

    def _update(self, clip: Clip) -> None:
        self.model.clip_changed(clip)
        if clip is self.current_clip():
            self._current_changed()

    def _settings_changed(self) -> None:
        clip = self.current_clip()
        if clip:
            self.model.clip_changed(clip)
            self.preview.refresh()      # mode may have changed → snapping, keyframe markers
            self.test_panel.refresh()   # the test may be stale now
            self.model.refresh_all()    # derived estimates of other clips
            self._plan_export()         # names contain speed, fps, codec …

    def _trim_changed(self) -> None:
        clip = self.current_clip()
        if clip:
            self.model.clip_changed(clip)
            self.settings.refresh()
            self.test_panel.refresh()
            self._plan_export()

    # ------------------------------------------------------------------ test encode

    def _start_test(self, n_frames: int) -> None:
        clip = self.current_clip()
        if not clip or clip.testing or not clip.frames:
            return
        try:
            test = testencode.TestEncode(clip.job, clip.playhead, n_frames,
                                         self.settings.supported_pix_fmts(clip))
        except (CommandError, ValueError) as e:
            QMessageBox.warning(self, "Test encode", f"These settings cannot be encoded:\n{e}")
            return
        testencode.discard(clip.test)
        clip.test = clip.test_media = None
        clip.testing = True
        self._tests[id(clip)] = test
        workers.start(workers.TestEncodeTask(clip, test, self.test_signals))
        self._update(clip)
        self.test_panel.refresh()

    def _cancel_test(self) -> None:
        clip = self.current_clip()
        if clip and id(clip) in self._tests:
            self._tests[id(clip)].cancel()

    def _test_progress(self, clip: Clip, progress) -> None:
        if clip is self.current_clip():
            self.test_panel.set_progress(progress)

    def _test_done(self, clip: Clip, result, media) -> None:
        self._tests.pop(id(clip), None)
        clip.testing = False
        if clip.removed:
            testencode.discard(result)
            return
        clip.test, clip.test_media = result, media
        self.model.refresh_all()
        if clip is self.current_clip():
            self.test_panel.refresh()

    def _update_batch(self, *_) -> None:
        clips = [c for c in self.model.clips if c.status != Status.ERROR]
        if not clips:
            self.batch_label.clear()
            return
        seconds, size, missing = self.model.batch_estimate()
        text = f"Batch: {len(clips)} clip(s)"
        if missing < len(clips):
            text += f" ≈ {fmt_seconds(seconds)}, {fmt_bytes(size)}"
        if missing:
            text += f" – {missing} without estimate (run a test encode)"
        self.batch_label.setText(text)

    def _apply_to_all(self) -> None:
        source = self.current_clip()
        if not source:
            return
        for clip in self.model.clips:
            if clip is not source:
                clip.settings = source.settings.clone()
                clip.ui = copy.deepcopy(source.ui)
        self.model.refresh_all()
        self._plan_export()
        others = len(self.model.clips) - 1
        self.statusBar().showMessage(f"Output settings (not the trim) of {source.path.name} "
                                     f"applied to {others} other clip(s)", 5000)

    # ------------------------------------------------------------------ export

    def _export_candidates(self) -> tuple[list[Clip], list[str]]:
        """Clips to export (in table order) and why others are left out."""
        clips = self.model.clips
        if self.export_panel.selected_only():
            rows = {i.row() for i in self.table.selectionModel().selectedRows()}
            clips = [c for i, c in enumerate(clips) if i in rows]
        ok, problems = [], []
        for clip in clips:
            if clip.status == Status.ERROR:
                problems.append(f"{clip.path.name} (cannot be read)")
            elif clip.status != Status.READY:
                problems.append(f"{clip.path.name} (still loading)")
            else:
                ok.append(clip)
        return ok, problems

    def _plan(self) -> tuple[list[Clip], list[str], list[batch.Item], list[str]]:
        """(clips, row labels, planned items, problems) for the current export scope."""
        panel = self.export_panel
        if panel.batch_list():
            entries = self.batch_entries
            clips = [e.clip for e in entries]
            labels = [e.label for e in entries]
            problems = [] if entries else [
                "the batch list is empty – use “Add to batch” in the Preview & trim tab"]
            # entries exported before keep their file; only the others are planned
            todo = [e for e in entries if not e.done]
            planned = iter(batch.plan([(_snapshot(e.job), e.pix_fmts) for e in todo],
                                      panel.output_folder(), panel.pattern_text(),
                                      panel.policy_key(), [e.additions for e in todo]))
            items = [batch.Item(e.job, e.exported, e.pix_fmts, "exported earlier", done=True)
                     if e.done else next(planned) for e in entries]
            return clips, labels, items, problems
        else:
            clips, problems = self._export_candidates()
            labels = [c.path.name for c in clips]
            # snapshot: changes made while the batch runs do not affect it
            jobs = [(_snapshot(c.job), self.settings.supported_pix_fmts(c)) for c in clips]
        items = batch.plan(jobs, panel.output_folder(), panel.pattern_text(), panel.policy_key())
        return clips, labels, items, problems

    def add_to_batch(self, clip: Clip) -> None:
        """Remember the clip as it is now (mode, settings, trim, sections) for the export."""
        if clip.status != Status.READY or not clip.info:
            return
        job = _snapshot(clip.job)
        additions = ()
        count = sum(e.clip is clip for e in self.batch_entries)
        if count:                       # another encoding: ask, offer name additions
            dialog = AdditionDialog(self, job, count, self.export_panel.pattern_text(),
                                    self.export_panel.output_folder())
            if not dialog.exec():
                return
            additions = dialog.keys()
        entry = BatchEntry(clip, job, f"{clip.path.name} – {batch.describe(job)}",
                           self.settings.supported_pix_fmts(clip), copy.deepcopy(clip.ui),
                           additions)
        self.batch_entries.append(entry)
        if not self._batch:
            self.export_panel.show_batch_list()
        self._plan_export()
        self.statusBar().showMessage(
            f"Added to the batch list: {entry.label} ({len(self.batch_entries)} in the list – "
            "Export tab)", 6000)

    def _remove_entries(self, rows: list[int]) -> None:
        if self._batch:
            return
        self.batch_entries = [e for i, e in enumerate(self.batch_entries) if i not in set(rows)]
        if self._editing and self._editing not in self.batch_entries:
            self._stop_editing()
        self._plan_export()

    def _open_entry(self, row: int) -> None:
        """Double-click in the batch list: load the entry into the editor – to change it or
        to start another encoding of the same clip."""
        if self._batch or not 0 <= row < len(self.batch_entries):
            return
        entry = self.batch_entries[row]
        clip = entry.clip
        if clip.removed or clip.status != Status.READY:
            return
        action = ask_entry_action(self, entry.label)
        if action is None:
            return
        self._stop_editing()
        clip.settings = entry.job.settings.clone()
        clip.ui = copy.deepcopy(entry.ui)
        clip.trim = copy.copy(entry.job.trim)
        clip.edit_segments(entry.job.segments, "open batch entry")
        self._select(clip)
        self._loaded(clip)
        self.tabs.setCurrentWidget(self.preview)
        if action == EDIT:
            self._editing = entry
            self.preview.set_editing(entry.label)
            text = "Change it, then click “✔ Update batch entry”"
        else:
            text = "Change it, then click “➕ Add to batch” for another encoding"
        self.statusBar().showMessage(f"Opened {entry.label}. {text}.", 10000)

    def _update_entry(self, clip: Clip) -> None:
        entry = self._editing
        if not entry or entry.clip is not clip or entry not in self.batch_entries:
            return
        entry.job = _snapshot(clip.job)
        entry.ui = copy.deepcopy(clip.ui)
        entry.pix_fmts = self.settings.supported_pix_fmts(clip)
        entry.label = f"{clip.path.name} – {batch.describe(entry.job)}"
        entry.exported = None                  # changed: export it again
        self._stop_editing()
        self._plan_export()
        self.statusBar().showMessage(f"Batch entry updated: {entry.label}", 6000)

    def _stop_editing(self) -> None:
        self._editing = None
        self.preview.set_editing(None)

    def _loaded(self, clip: Clip) -> None:
        """Settings, trim and sections of `clip` were replaced from outside."""
        self._update(clip)
        if clip is self.current_clip():
            self.preview.sections_replaced()
        self._trim_changed()

    # ------------------------------------------------------------------ treatments (.cst)

    def load_treatment_dialog(self) -> None:
        clip = self.current_clip()
        start = str(clip.path.with_suffix(treatment.SUFFIX)) if clip else ""
        path, _ = QFileDialog.getOpenFileName(self, "Load Clip Speed Treatment", start,
                                              CST_FILTER)
        if path:
            self.open_treatment(Path(path))

    def save_treatment(self) -> None:
        clip = self.current_clip()
        if not clip or clip.status != Status.READY:
            self.statusBar().showMessage("Select a loaded clip to save its treatment", 5000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Clip Speed Treatment", str(clip.path.with_suffix(treatment.SUFFIX)),
            CST_FILTER)
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != treatment.SUFFIX:
            target = target.with_name(target.name + treatment.SUFFIX)
        try:
            treatment.save(target, clip.path, clip.frames.count, clip.settings, clip.ui,
                           clip.trim, clip.segments)
        except OSError as e:
            QMessageBox.warning(self, "Save Clip Speed Treatment", f"Could not save {target.name}:\n{e}")
            return
        n = len(clip.segments)
        self.statusBar().showMessage(f"Saved {target.name} ({n} section{'s' * (n != 1)}, trim "
                                     "and output settings)", 6000)

    def open_treatment(self, path: Path) -> None:
        """Load a .cst onto the video it belongs to: the current clip, another clip in the
        list, or – if it is not in the list – the file it was saved from (added first)."""
        try:
            t = treatment.load(path)
        except treatment.TreatmentError as e:
            QMessageBox.warning(self, "Load Clip Speed Treatment", str(e))
            return
        clips = [self.current_clip()] + [c for c in self.model.clips if c is not self.current_clip()]
        for clip in clips:
            if clip and clip.status != Status.ERROR and self._matches(clip.path, t):
                if clip.status == Status.READY:
                    self._apply_treatment(clip, path, t)
                else:
                    self._pending[clip.path] = (path, t)
                    self._select(clip)
                return
        # not in the list: the place it was saved from, or next to the .cst
        for candidate in (Path(t.source_path) if t.source_path else None,
                          path.parent / t.source_name):
            if candidate and candidate.is_file() and self._matches(candidate, t):
                candidate = candidate.resolve()
                self._pending[candidate] = (path, t)
                self.add_files([candidate])
                if (clip := self._clip(candidate)):
                    self._select(clip)
                return
        QMessageBox.warning(
            self, "Load Clip Speed Treatment",
            f"{path.name} belongs to {t.source_name} ({t.source_size:,} bytes, {t.frames} "
            "frames).\n\nNone of the clips in the list is that video, and it was not found "
            "where it was saved. Add the video first (a renamed copy works too), then load "
            "the treatment again.")

    @staticmethod
    def _matches(path: Path, t: treatment.Treatment) -> bool:
        try:
            return path.stat().st_size == t.source_size and \
                treatment.fingerprint(path) == t.fingerprint
        except OSError:
            return False

    def _apply_treatment(self, clip: Clip, path: Path, t: treatment.Treatment) -> None:
        try:
            t.check(clip.path, clip.frames.count)
        except (treatment.TreatmentError, OSError) as e:
            QMessageBox.warning(self, "Load Clip Speed Treatment", str(e))
            return
        if clip.segments:
            n = len(clip.segments)
            answer = QMessageBox.question(
                self, "Load Clip Speed Treatment",
                f"Replace the {n} speed section{'s' * (n != 1)}, the trim and the output "
                f"settings of {clip.path.name} with {path.name}?\n\n"
                "The current sections can be brought back with “↶ Undo”.",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return
        if self._editing and self._editing.clip is clip:
            self._stop_editing()
        clip.settings = t.settings.clone()
        clip.ui = copy.deepcopy(t.ui)
        clip.trim = copy.copy(t.trim)
        clip.edit_segments(t.segments, f"load {path.name}")
        self._select(clip)
        self._loaded(clip)
        self.tabs.setCurrentWidget(self.preview)
        text = f"Loaded {path.name} onto {clip.path.name}"
        st = self.settings.encoders.get(clip.settings.codec) if self.settings.encoders else None
        if st is not None and not st.available:
            QMessageBox.information(
                self, "Load Clip Speed Treatment",
                f"{text}.\n\nIts codec ({CODECS_BY_KEY[clip.settings.codec].label}) is not "
                f"available on this computer ({st.reason}). Choose another codec before "
                "exporting.")
        self.statusBar().showMessage(text, 6000)

    def _plan_export(self, *_) -> None:
        if self._batch or not hasattr(self, "export_panel"):
            return
        clips, labels, items, problems = self._plan()
        if self.settings.encoders is None and clips:
            problems.append("waiting for encoder detection")
        self.export_panel.show_plan(labels, items, problems)
        if self.settings.encoders is None:
            self.export_panel.start_button.setEnabled(False)

    def start_export(self) -> None:
        if self._batch or self.settings.encoders is None:
            return
        clips, labels, items, problems = self._plan()
        if not any(it.output and not it.done for it in items):
            return
        folder = self.export_panel.output_folder()
        if folder is not None:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, "Export", f"Cannot create the output folder:\n{e}")
                return
        self.export_panel.show_plan(labels, items, problems)
        self._batch = batch.Batch(items)
        self._batch_clips = clips
        self._batch_entries = list(self.batch_entries) if self.export_panel.batch_list() else None
        # a clip's estimate only fits a batch entry made with the clip's current settings
        self._batch_estimates = [e.seconds if (e := self.model.estimate(c))
                                 and it.job.settings == c.settings else None
                                 for c, it in zip(clips, items)]
        self._batch_done_frames = 0
        self._batch_start = time.monotonic()
        for clip, item in zip(clips, items):
            if item.done:
                continue
            clip.export = "Queued" if item.output else "Skipped (file exists)"
            self.model.clip_changed(clip)
        for action in self._list_actions:
            action.setEnabled(False)
        self.export_panel.set_running(True)
        workers.start(workers.BatchTask(self._batch, self.batch_signals))

    def _cancel_export(self) -> None:
        if self._batch:
            self._batch.cancel()
            self.export_panel.cancel_button.setEnabled(False)
            self.export_panel.message.setText("Cancelling…")

    def _export_started(self, index: int) -> None:
        self.export_panel.set_status(index, "running")
        clip = self._batch_clips[index]
        clip.export = "Encoding 0 %"
        self.model.clip_changed(clip)

    def _export_progress(self, index: int, p) -> None:
        if not self._batch:
            return
        clip = self._batch_clips[index]
        clip.export = f"Encoding {p.fraction:.0%}"
        self.model.clip_changed(clip)
        clip_text = f"{p.frame}/{p.total_frames} frames, {p.fps:.1f} fps"
        if p.eta is not None:
            clip_text += f", {fmt_seconds(p.eta)} left"
        total = max(1, self._batch.total_frames)
        overall = min(1.0, (self._batch_done_frames + p.frame) / total)
        overall_text = f"{fmt_seconds(time.monotonic() - self._batch_start)} elapsed"
        later = [self._batch_estimates[i] for i, it in enumerate(self._batch.items)
                 if i > index and it.output and not it.done]
        if p.eta is not None and None not in later:
            overall_text += f", ≈ {fmt_seconds(p.eta + sum(later))} left"
        self.export_panel.set_progress(clip.path.name, p.fraction, clip_text,
                                       overall, overall_text)

    def _export_item_done(self, r: batch.ItemResult) -> None:
        if not self._batch:
            return
        item = self._batch.items[r.index]
        if item.output:
            self._batch_done_frames += item.job.output_frame_count
        detail = fmt_seconds(r.elapsed) if r.status == "done" else ""
        if r.status == "skipped":
            detail = item.note.removeprefix("skipped: ")
        self.export_panel.set_status(r.index, r.status, detail)
        self.export_panel.set_error(r.index, r.error)
        if r.status == "done" and self._batch_entries:
            self._batch_entries[r.index].exported = r.output
        clip = self._batch_clips[r.index]
        clip.export = {"done": "Exported", "failed": "Export failed",
                       "cancelled": "Export cancelled", "skipped": "Skipped (file exists)"}[r.status]
        self.model.clip_changed(clip)

    def _export_finished(self, result: batch.BatchResult) -> None:
        elapsed = time.monotonic() - self._batch_start
        self._batch = None
        self._batch_entries = None
        for action in self._list_actions:
            action.setEnabled(True)
        self.export_panel.finished(result, elapsed)
        self.statusBar().showMessage(self.export_panel.message.text(), 10000)
