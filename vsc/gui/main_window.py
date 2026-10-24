"""Main window: clip table on top; below, preview / clip info tabs next to the output settings."""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMainWindow,
                               QMessageBox, QSplitter, QTableView, QTabWidget, QToolBar)

from ..core import testencode
from ..core.command import CommandError
from ..core.formats import CODECS_BY_KEY
from .clips import Clip, ClipModel, Status, fmt_bytes, fmt_seconds
from .info_panel import InfoPanel
from .settings_panel import SettingsPanel
from .test_panel import TestPanel
from .timeline import PreviewPanel
from . import workers

VIDEO_FILTER = ("Video files (*.mp4 *.mov *.mkv *.avi *.mts *.m2ts *.mxf *.webm *.m4v *.wmv "
                "*.flv *.360 *.lrv *.MP4 *.MOV *.MKV *.AVI *.MTS);;All files (*)")


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
        self.tabs = QTabWidget()
        self.tabs.addTab(self.preview, "Preview && trim")
        self.test_panel = TestPanel()
        self.test_panel.start_test.connect(self._start_test)
        self.test_panel.cancel_test.connect(self._cancel_test)
        self.tabs.addTab(self.test_panel, "Test encode")
        self.tabs.addTab(self.info, "Clip info")
        self.tabs.currentChanged.connect(lambda: self.test_panel.refresh())  # playhead may have moved
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
        for action in (add, remove, clear):
            toolbar.addAction(action)

        self.batch_label = QLabel()
        self.statusBar().addPermanentWidget(self.batch_label)
        for sig in (self.model.dataChanged, self.model.rowsInserted, self.model.rowsRemoved):
            sig.connect(self._update_batch)
        self.statusBar().showMessage("Detecting encoders…")
        self.clip_signals = workers.ClipSignals(self)
        self.clip_signals.probed.connect(self._probed)
        self.clip_signals.scanned.connect(self._scanned)
        self.clip_signals.failed.connect(self._failed)
        self.thumb_signals = workers.ThumbnailSignals(self)
        self.thumb_signals.thumbnail.connect(self._thumbnail)
        self.test_signals = workers.TestSignals(self)
        self.test_signals.progress.connect(self._test_progress)
        self.test_signals.done.connect(self._test_done)
        self.encoder_signals = workers.EncoderSignals(self)
        self.encoder_signals.done.connect(self._encoders_done)
        self.encoder_signals.failed.connect(
            lambda msg: self.statusBar().showMessage(f"Encoder detection failed: {msg}"))
        workers.start(workers.EncoderDetector(self.encoder_signals))

    def closeEvent(self, event) -> None:
        for test in self._tests.values():
            test.cancel()
        for clip in self.model.clips:
            clip.removed = True          # stops thumbnail loaders
            testencode.discard(clip.test)
        super().closeEvent(event)

    # ------------------------------------------------------------------ import

    def add_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add video files", "", VIDEO_FILTER)
        self.add_files([Path(f) for f in files])

    def add_files(self, paths: list[Path]) -> None:
        first_new = None
        for path in paths:
            if path.is_dir():
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
        self._current_changed(self.table.currentIndex())

    def clear(self) -> None:
        self.model.remove_rows(list(range(len(self.model.clips))))
        self._current_changed(self.table.currentIndex())

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
            self._update(clip)

    def _failed(self, path, message: str) -> None:
        clip = self._clip(path)
        if clip:
            clip.status, clip.error = Status.ERROR, message
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

    def _trim_changed(self) -> None:
        clip = self.current_clip()
        if clip:
            self.model.clip_changed(clip)
            self.settings.refresh()
            self.test_panel.refresh()

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
        others = len(self.model.clips) - 1
        self.statusBar().showMessage(f"Output settings (not the trim) of {source.path.name} "
                                     f"applied to {others} other clip(s)", 5000)
