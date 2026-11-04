# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""'Convert videos' window: re-encode many files (or whole folders), independent of the clip
list and the slow-motion settings of the main window (`core/convert.py`).

Easy: codec, quality level, sound on / off, optional "Smart" (measured per video,
`core/suggest.py`). Pro (user request 2026-11-04): frame rate, container, codec, quality level /
own quality value / kbit/s / smart, sound codec, channels and kbit/s – general settings for
every video, and own settings for selected videos ("Own settings for selected").
"""
from __future__ import annotations

import json
import time
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QDialog, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import audio, batch, convert, formats, suggest
from ..core.convert import ConvertSettings
from ..core.probe import probe, scan_frames
from .clips import fmt_bytes, fmt_seconds
from .settings_panel import Combo
from . import workers

COLUMNS = ("File", "Length", "Size", "Settings", "Status")
_FILE, _LENGTH, _SIZE, _SETTINGS, _STATUS = range(5)

AUDIO_CHOICES = (
    ("smart", "Smart – copy if possible, else matched AAC"),
    ("copy", "Copy unchanged"),
    ("aac", "AAC"),
    ("opus", "Opus"),
    ("mp3", "MP3"),
    ("flac", "FLAC (lossless)"),
    ("none", "No sound"),
)
CHANNEL_CHOICES = ((None, "Like the original"), (1, "Mono"), (2, "Stereo"),
                   (6, "5.1 (6 channels)"), (8, "7.1 (8 channels)"))
RATE_CHOICES = (("level", "Quality level"), ("crf", "Own quality value"),
                ("kbps", "Data rate (kbit/s)"), ("smart", "Smart – measured per video"))


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


class _MeasureSignals(QObject):
    progress = Signal(object, float, str)    # path, fraction, text
    done = Signal(object, object, object)    # path, key, Suggestion
    failed = Signal(object, object, str)     # path, key, message
    finished = Signal(bool)                  # cancelled


class _Measure(QRunnable):
    """Measures the videos one after another (each uses every CPU core)."""

    def __init__(self, tasks: list[tuple], pix: dict, signals: _MeasureSignals):
        super().__init__()
        self.tasks, self.pix, self.signals = tasks, pix, signals
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        for path, info, frames, key in self.tasks:
            if self._cancel:
                break
            codec, goal, container = key
            try:
                s = suggest.suggest(info, frames, codec, goal, container, self.pix.get(codec),
                                    progress=lambda f, t, p=path: workers._emit(
                                        self.signals.progress, p, f, t),
                                    cancelled=lambda: self._cancel)
                workers._emit(self.signals.done, path, key, s)
            except Exception as e:  # noqa: BLE001 – shown in the row
                if not self._cancel:
                    workers._emit(self.signals.failed, path, key, str(e).strip()[-300:])
        workers._emit(self.signals.finished, self._cancel)


class _Row:
    def __init__(self, path: Path):
        self.path = path
        self.info = None
        self.frames = None
        self.error = ""
        self.status = "Reading…"
        self.output: Path | None = None      # converted file (not converted again)
        self.own: ConvertSettings | None = None      # pro mode: own settings for this video

    @property
    def todo(self) -> bool:
        return self.info is not None and not (self.output and self.output.exists())


def _measure_key(cs: ConvertSettings) -> tuple[str, str, str]:
    return cs.codec, cs.goal, cs.container


def settings_to_json(cs: ConvertSettings) -> str:
    d = dict(cs.__dict__)
    d["fps"] = str(cs.fps) if cs.fps is not None else None
    return json.dumps(d)


def settings_from_json(text: str) -> ConvertSettings:
    try:
        d = json.loads(text)
        known = ConvertSettings.__dataclass_fields__
        d = {k: v for k, v in d.items() if k in known}
        if d.get("fps"):
            d["fps"] = Fraction(d["fps"])
        cs = ConvertSettings(**d)
    except (ValueError, TypeError):
        return ConvertSettings(audio="smart")
    if cs.codec not in convert.CODECS:
        cs.codec = convert.DEFAULT_CODEC
    if cs.rate not in convert.RATE_MODES:
        cs.rate = "level"
    if cs.audio not in convert.AUDIO_MODES:
        cs.audio = "smart"
    return cs


class SettingsEditor(QWidget):
    """The settings form: Easy (codec, quality, smart, sound) or Pro (everything)."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self.pro = False
        self._status = None
        # --- shared
        self.codec = Combo()
        self.codec.setToolTip("Video codec of the converted files.")
        self.level = Combo()
        for name, tip in formats.QUALITY_LEVELS:
            self.level.addItem(name)
            self.level.setItemData(self.level.count() - 1, tip, Qt.ToolTipRole)
        self.goal = Combo()
        for key in convert.GOALS:
            self.goal.addItem(suggest.GOAL_LABELS[key], key)
        self.goal.setToolTip(
            "Looks identical: the smallest file without a visible difference (VMAF ≥ 96).\n"
            "Smaller, minimal loss: noticeably smaller, a slight loss only on a close look "
            "(VMAF ≥ 93).")
        # --- easy
        self.smart = QCheckBox("Smart: smallest file that keeps picture and sound")
        self.smart.setToolTip(
            "Each video is measured first: short samples are encoded at several quality\n"
            "values and compared with the original (VMAF). The smallest one that keeps the\n"
            "picture is used. The sound is copied unchanged when possible.\n"
            "Measuring takes about 20 s per small video, longer for HD.")
        self.sound = QCheckBox("Keep the sound")
        # --- pro
        self.fps = Combo()
        self.fps.addItem("Original (each video's own)", None)
        for label, rate in formats.FRAME_RATES:
            self.fps.addItem(f"{label} fps", str(rate))
        self.fps.setToolTip("Another frame rate keeps the length: frames are dropped or "
                            "repeated, never invented.")
        self.container = Combo()
        for c in convert.CONTAINERS:
            self.container.addItem(c.upper(), c)
        self.rate = Combo()
        for key, label in RATE_CHOICES:
            self.rate.addItem(label, key)
        self.crf = QSpinBox()
        self.crf.setToolTip("The codec's own quality value (CRF): lower = better and bigger.")
        self.kbps = QSpinBox()
        self.kbps.setRange(20, 200000)
        self.kbps.setSingleStep(50)
        self.kbps.setSuffix(" kbit/s")
        self.kbps.setToolTip("Average data rate of the picture.")
        self.audio = Combo()
        for key, label in AUDIO_CHOICES:
            self.audio.addItem(label, key)
        self.channels = Combo()
        for ch, label in CHANNEL_CHOICES:
            self.channels.addItem(label, ch)
        self.channels.setToolTip("Never more than the original has – more channels would only "
                                 "repeat the same sound.")
        self.audio_kbps = QSpinBox()
        self.audio_kbps.setRange(0, 512)
        self.audio_kbps.setSingleStep(16)
        self.audio_kbps.setSuffix(" kbit/s")
        self.audio_kbps.setSpecialValueText("Default")
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet("color: #c0392b")

        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self._rows = {}
        for key, label, w in (("fps", "Frame rate:", self.fps), ("container", "Container:", self.container),
                              ("codec", "Codec:", self.codec), ("rate", "Picture:", self.rate),
                              ("level", "Quality:", self.level), ("crf", "Quality value:", self.crf),
                              ("kbps", "Data rate:", self.kbps), ("smart", "", self.smart),
                              ("goal", "Smart goal:", self.goal), ("sound", "", self.sound),
                              ("audio", "Sound:", self.audio), ("channels", "Channels:", self.channels),
                              ("audio_kbps", "Sound rate:", self.audio_kbps),
                              ("problem", "", self.problem)):
            self.form.addRow(label, w)
            self._rows[key] = w
        for w in (self.codec, self.level, self.goal, self.fps, self.container, self.rate,
                  self.audio, self.channels):
            w.currentIndexChanged.connect(self._edited)
        for w in (self.crf, self.kbps, self.audio_kbps):
            w.valueChanged.connect(self._edited)
        for w in (self.smart, self.sound):
            w.toggled.connect(self._edited)

    # ------------------------------------------------------------------ helpers
    def set_codec_status(self, status) -> None:
        self._status = status
        self._busy = True
        current = self.codec.currentData()
        self.codec.clear()
        for key in convert.CODECS:
            codec = formats.CODECS_BY_KEY[key]
            st = status.get(key) if status else None
            ok = st is None or st.available
            self.codec.addItem(codec.label if ok else f"{codec.label} – not available", key)
            if not ok:
                self.codec.model().item(self.codec.count() - 1).setEnabled(False)
        if current:
            self.codec.setCurrentIndex(max(0, self.codec.findData(current)))
        self._busy = False

    def codec_ok(self, key: str) -> bool:
        st = self._status.get(key) if self._status else None
        return st is None or st.available

    def _show(self, key: str, visible: bool) -> None:
        w = self._rows[key]
        w.setVisible(visible)
        label = self.form.labelForField(w)
        if label:
            label.setVisible(visible)

    def _update_visibility(self) -> None:
        pro = self.pro
        rate = self.rate.currentData()
        a = self.audio.currentData()
        smart_easy = self.smart.isChecked()
        self._show("fps", pro)
        self._show("container", pro)
        self._show("rate", pro)
        self._show("level", (pro and rate == "level") or (not pro and not smart_easy))
        self._show("crf", pro and rate == "crf")
        self._show("kbps", pro and rate == "kbps")
        self._show("smart", not pro)
        self._show("goal", (pro and (rate == "smart" or a == "smart")) or (not pro and smart_easy))
        self._show("sound", not pro)
        self._show("audio", pro)
        self._show("channels", pro and a in audio.ENCODERS)
        self._show("audio_kbps", pro and a in audio.ENCODERS and a != "flac")
        self._show("problem", pro and bool(self.problem.text()))

    def _limits(self) -> None:
        """Codec-dependent ranges and allowed containers / sound codecs."""
        key = self.codec.currentData()
        codec = formats.CODECS_BY_KEY.get(key)
        allowed = convert.containers_for(key) if key else []
        for i in range(self.container.count()):
            self.container.model().item(i).setEnabled(self.container.itemData(i) in allowed)
        if self.container.currentData() not in allowed and allowed:
            self.container.setCurrentIndex(self.container.findData(allowed[0]))
        if codec and codec.quality:
            self.crf.setRange(codec.quality.minimum, codec.quality.maximum)
        cont = self.container.currentData()
        for i in range(self.audio.count()):
            k = self.audio.itemData(i)
            self.audio.model().item(i).setEnabled(
                k not in audio.ENCODERS or audio.encode_reason(cont, k) is None)
        if self.audio.currentData() in audio.ENCODERS and \
                audio.encode_reason(cont, self.audio.currentData()):
            self.audio.setCurrentIndex(self.audio.findData("aac"))

    def _edited(self, *_) -> None:
        if self._busy:
            return
        self._busy = True
        self._limits()
        self._busy = False
        self._update_visibility()
        self.changed.emit()

    # ------------------------------------------------------------------ in / out
    def set_settings(self, cs: ConvertSettings, pro: bool) -> None:
        self._busy = True
        self.pro = pro
        self.codec.setCurrentIndex(max(0, self.codec.findData(cs.codec)))
        self._limits()
        self.level.setCurrentIndex(min(max(cs.level, 0), self.level.count() - 1))
        self.goal.setCurrentIndex(max(0, self.goal.findData(cs.goal)))
        self.smart.setChecked(cs.rate == "smart")
        self.sound.setChecked(cs.audio != "none")
        self.fps.setCurrentIndex(max(0, self.fps.findData(str(cs.fps) if cs.fps else None)))
        self.container.setCurrentIndex(max(0, self.container.findData(cs.container)))
        self.rate.setCurrentIndex(max(0, self.rate.findData(cs.rate)))
        codec = formats.CODECS_BY_KEY.get(cs.codec)
        self.crf.setValue(cs.crf if cs.crf is not None else
                          (convert.quality_value(cs.codec, cs.level) or
                           (codec.quality.default if codec and codec.quality else 0)))
        self.kbps.setValue(cs.kbps or 1000)
        audio_key = "smart" if cs.audio == "default" else cs.audio
        self.audio.setCurrentIndex(max(0, self.audio.findData(audio_key)))
        self.channels.setCurrentIndex(max(0, self.channels.findData(cs.channels)))
        self.audio_kbps.setValue(cs.audio_kbps or 0)
        self._limits()
        self._busy = False
        self._update_visibility()

    def settings(self) -> ConvertSettings:
        if not self.pro:
            smart = self.smart.isChecked()
            sound = self.sound.isChecked()
            return ConvertSettings(
                codec=self.codec.currentData() or convert.DEFAULT_CODEC,
                rate="smart" if smart else "level", level=self.level.currentIndex(),
                goal=self.goal.currentData(),
                audio=("smart" if smart else "default") if sound else "none")
        fps = self.fps.currentData()
        return ConvertSettings(
            codec=self.codec.currentData() or convert.DEFAULT_CODEC,
            container=self.container.currentData(),
            fps=Fraction(fps) if fps else None,
            rate=self.rate.currentData(), level=self.level.currentIndex(),
            crf=self.crf.value(), kbps=self.kbps.value(), goal=self.goal.currentData(),
            audio=self.audio.currentData(), channels=self.channels.currentData(),
            audio_kbps=self.audio_kbps.value() or None)

    def set_problem(self, text: str) -> None:
        self.problem.setText(text)
        self._update_visibility()


class ConvertDialog(QDialog):
    """`encoders()` returns the main window's encoder status (None while it is detected)."""

    def __init__(self, parent=None, encoders=lambda: None):
        super().__init__(parent)
        self.setWindowTitle("Convert videos")
        self.setAcceptDrops(True)
        self.resize(900, 760)
        self._encoders = encoders
        self.rows: list[_Row] = []
        self._batch: batch.Batch | None = None
        self._items: list[batch.Item] = []
        self._row_of_item: list[int] = []
        self._frames_before: list[int] = []
        self._start = 0.0
        self._measured: dict[tuple, suggest.Suggestion] = {}     # (path, key) → result
        self._measure_failed: dict[tuple, str] = {}
        self._measure: _Measure | None = None
        self._convert_after_measure = False
        self._editing: list[int] = []          # rows whose own settings the editor shows
        self._probe_signals = _ProbeSignals(self)
        self._probe_signals.done.connect(self._probed)
        self._probe_signals.failed.connect(self._probe_failed)
        self._measure_signals = _MeasureSignals(self)
        self._measure_signals.progress.connect(self._measure_progress)
        self._measure_signals.done.connect(self._measure_done)
        self._measure_signals.failed.connect(self._measure_error)
        self._measure_signals.finished.connect(self._measure_finished)
        self._batch_signals = workers.BatchSignals(self)
        self._batch_signals.started.connect(self._item_started)
        self._batch_signals.progress.connect(self._item_progress)
        self._batch_signals.item_done.connect(self._item_done)
        self._batch_signals.finished.connect(self._finished)
        qs = QSettings()
        self.easy_settings = settings_from_json(qs.value("convert/easy", "", type=str)) \
            if qs.value("convert/easy", "", type=str) else self._old_easy(qs)
        self.general = settings_from_json(qs.value("convert/general", "", type=str)) \
            if qs.value("convert/general", "", type=str) else ConvertSettings(audio="smart")

        intro = QLabel("Re-encodes many videos at once. Add files or whole folders – or drop "
                       "them here. The originals stay unchanged.")
        intro.setWordWrap(True)
        self.easy_radio = QRadioButton("Easy")
        self.pro_radio = QRadioButton("Pro")
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.easy_radio)
        mode_group.addButton(self.pro_radio)
        (self.pro_radio if qs.value("convert/pro", False, type=bool) else self.easy_radio).setChecked(True)
        self.pro_radio.toggled.connect(self._mode_changed)
        top = QHBoxLayout()
        top.addWidget(intro, 1)
        top.addWidget(self.easy_radio)
        top.addWidget(self.pro_radio)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(_FILE, QHeaderView.Stretch)
        for c in (_LENGTH, _SIZE):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        for c in (_SETTINGS, _STATUS):
            head.setSectionResizeMode(c, QHeaderView.Interactive)
        self.table.setColumnWidth(_SETTINGS, 230)
        self.table.setColumnWidth(_STATUS, 200)
        self.table.itemSelectionChanged.connect(self._selection_changed)

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

        self.own_button = QPushButton("Own settings for selected", clicked=self._make_own)
        self.own_button.setToolTip("The selected videos get their own settings (starting from the "
                                   "general ones). Select them again later to change them.")
        self.general_button = QPushButton("Back to general settings", clicked=self._drop_own)
        self.measure_button = QPushButton("Measure now", clicked=self._measure_now)
        self.measure_button.setToolTip("Measure the videos for the smart settings now (it also "
                                       "happens automatically before converting).")
        own_row = QHBoxLayout()
        own_row.addWidget(self.own_button)
        own_row.addWidget(self.general_button)
        own_row.addStretch(1)
        own_row.addWidget(self.measure_button)

        # settings
        self.editor = SettingsEditor()
        self.editor.set_codec_status(self._encoders())
        self.editor.changed.connect(self._editor_changed)
        self.settings_box = QGroupBox()
        box = QVBoxLayout(self.settings_box)
        box.addWidget(self.editor)

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
        save = QFormLayout()
        save.addRow("Save to:", self.next_to)
        save.addRow("", _wrap(folder_row))
        note = QLabel("Existing files are never overwritten: a number is added (name_2 …).")
        note.setStyleSheet("color: gray")
        save.addRow("", note)

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
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addLayout(list_row)
        lay.addLayout(own_row)
        lay.addWidget(self.settings_box)
        lay.addLayout(save)
        lay.addWidget(self.progress)
        lay.addLayout(bottom)
        self._load_editor()

    @staticmethod
    def _old_easy(qs) -> ConvertSettings:
        """Easy settings from the 0.9.4 keys (codec / level / sound)."""
        codec = qs.value("convert/codec", convert.DEFAULT_CODEC, type=str)
        return ConvertSettings(codec=codec if codec in convert.CODECS else convert.DEFAULT_CODEC,
                               level=qs.value("convert/level", convert.DEFAULT_LEVEL, type=int),
                               audio="default" if qs.value("convert/sound", True, type=bool)
                               else "none")

    # ------------------------------------------------------------------ settings

    @property
    def pro(self) -> bool:
        return self.pro_radio.isChecked()

    def refresh_codecs(self) -> None:
        """Called when the encoder detection has finished."""
        self.editor.set_codec_status(self._encoders())
        self._load_editor()

    def _mode_changed(self) -> None:
        QSettings().setValue("convert/pro", self.pro)
        self._load_editor()

    def _selected(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def _load_editor(self) -> None:
        """Show the general settings, or the own settings of the selected videos."""
        sel = self._selected()
        own = [i for i in sel if self.rows[i].own is not None]
        self._editing = own if self.pro and own and len(own) == len(sel) else []
        if not self.pro:
            self.settings_box.setTitle("Settings for every video")
            self.editor.set_settings(self.easy_settings, False)
        elif self._editing:
            names = ", ".join(self.rows[i].path.name for i in self._editing[:2])
            more = f" and {len(self._editing) - 2} more" if len(self._editing) > 2 else ""
            self.settings_box.setTitle(f"Own settings: {names}{more}")
            self.editor.set_settings(self.rows[self._editing[0]].own, True)
        else:
            self.settings_box.setTitle("General settings – for every video without own settings")
            self.editor.set_settings(self.general, True)
        self._update_buttons()
        self._refresh()

    def _editor_changed(self) -> None:
        cs = self.editor.settings()
        qs = QSettings()
        if not self.pro:
            self.easy_settings = cs
            qs.setValue("convert/easy", settings_to_json(cs))
        elif self._editing:
            for i in self._editing:
                self.rows[i].own = cs.copy()
                self._show(i)
        else:
            self.general = cs
            qs.setValue("convert/general", settings_to_json(cs))
            for i, r in enumerate(self.rows):
                if r.own is None:
                    self._show(i)
        self._refresh()

    def _selection_changed(self) -> None:
        if self.pro:
            self._load_editor()
        self._update_buttons()

    def _update_buttons(self) -> None:
        sel = self._selected()
        running = self._busy()
        for w in (self.own_button, self.general_button):
            w.setVisible(self.pro)
        self.own_button.setEnabled(bool(sel) and not running)
        self.general_button.setEnabled(any(self.rows[i].own for i in sel) and not running)

    def settings_for(self, row: _Row) -> ConvertSettings:
        if not self.pro:
            return self.easy_settings
        return row.own or self.general

    def _make_own(self) -> None:
        for i in self._selected():
            if self.rows[i].own is None:
                self.rows[i].own = self.general.copy()
            self._show(i)
        self._load_editor()

    def _drop_own(self) -> None:
        for i in self._selected():
            self.rows[i].own = None
            self._show(i)
        self._load_editor()

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
        for c in (_LENGTH, _SIZE, _SETTINGS, _STATUS):
            self.table.setItem(r, c, QTableWidgetItem(""))
        self._show(r)

    def measured(self, row: _Row) -> suggest.Suggestion | None:
        cs = self.settings_for(row)
        return self._measured.get((row.path, _measure_key(cs))) if cs.measures else None

    def _settings_text(self, row: _Row) -> tuple[str, str]:
        """(cell text, tooltip) of the Settings column."""
        cs = self.settings_for(row)
        base = ("Own: " + convert.describe(cs)) if (self.pro and row.own) else (
            "General" if self.pro else "")
        tip = convert.describe(cs)
        if cs.measures and row.info is not None:
            key = (row.path, _measure_key(cs))
            if key in self._measured:
                s = self._measured[key]
                share = s.size_bytes / row.info.size_bytes * 100 if row.info.size_bytes else 0
                short = f"quality {s.crf} ≈ {s.video_kbps} kbit/s, ~{share:.0f} %"
                tip += "\nSmart: " + s.summary(row.info)
                base = f"{base} – {short}" if base else short
            elif key in self._measure_failed:
                base = (base + " – " if base else "") + "measuring failed"
                tip += "\n" + self._measure_failed[key]
            else:
                base = (base + " – " if base else "") + "not measured yet"
        problem = convert.audio_problem(row.info, cs) if row.info else None
        if problem:
            base = "⚠ " + base
            tip += "\n" + problem
        return base, tip

    def _show(self, r: int) -> None:
        row = self.rows[r]
        info = row.info
        self.table.item(r, _LENGTH).setText(fmt_seconds(info.duration) if info else "")
        self.table.item(r, _SIZE).setText(fmt_bytes(info.size_bytes) if info else "")
        text, tip = self._settings_text(row)
        cell = self.table.item(r, _SETTINGS)
        cell.setText(text)
        cell.setToolTip(tip)
        status = self.table.item(r, _STATUS)
        status.setText(row.status)
        status.setToolTip(row.error or (f"{info.codec} {info.width}×{info.height} "
                                        f"{float(info.fps):.5g} fps"
                                        + (f", sound {info.audio}" if info.audio else "")
                                        if info else ""))

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
        for r in reversed(self._selected()):
            self.table.removeRow(r)
            del self.rows[r]
        self._load_editor()

    def _clear(self) -> None:
        self.table.setRowCount(0)
        self.rows.clear()
        self._load_editor()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and not self._busy():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.add_paths([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()

    # ------------------------------------------------------------------ measuring

    def _busy(self) -> bool:
        return self._batch is not None or self._measure is not None

    def _pix(self) -> dict:
        status = self._encoders()
        return {k: (status[k].pix_fmts or None) for k in convert.CODECS
                if status and k in status}

    def _unmeasured(self) -> list[int]:
        out = []
        for i in self._ready_rows():
            r = self.rows[i]
            cs = self.settings_for(r)
            if cs.measures and (r.path, _measure_key(cs)) not in self._measured:
                out.append(i)
        return out

    def _measure_now(self) -> None:
        if self._measure:
            self._measure.cancel()
            return
        self._start_measuring(convert_after=False)

    def _start_measuring(self, convert_after: bool) -> bool:
        todo = self._unmeasured()
        if not todo:
            return False
        if not suggest.vmaf_available():
            QMessageBox.warning(self, "Convert videos", "This FFmpeg has no VMAF – smart "
                                "settings cannot be measured.")
            return False
        tasks = []
        for i in todo:
            r = self.rows[i]
            key = _measure_key(self.settings_for(r))
            self._measure_failed.pop((r.path, key), None)
            tasks.append((r.path, r.info, r.frames, key))
            r.status = "Waiting to be measured"
            self._show(i)
        self._measure_total = len(tasks)
        self._measure_count = 0
        self._convert_after_measure = convert_after
        self._measure = _Measure(tasks, self._pix(), self._measure_signals)
        self._start = time.monotonic()
        self._set_running(True)
        workers.start(self._measure)
        return True

    def _measure_progress(self, path, fraction: float, text: str) -> None:
        i = self._index(path)
        if i is None:
            return
        self.rows[i].status = f"Measuring… {fraction * 100:.0f} %"
        self.table.item(i, _STATUS).setText(self.rows[i].status)
        self.table.item(i, _STATUS).setToolTip(text)
        done = self._measure_count + fraction
        self.progress.setValue(int(1000 * done / max(1, self._measure_total)))
        self.summary.setText(f"Measuring video {self._measure_count + 1} of "
                             f"{self._measure_total} – {text}")

    def _measure_done(self, path, key, s) -> None:
        self._measured[(path, key)] = s
        self._measure_count += 1
        i = self._index(path)
        if i is not None:
            self.rows[i].status = "Measured"
            self._show(i)

    def _measure_error(self, path, key, message: str) -> None:
        self._measure_failed[(path, key)] = message
        self._measure_count += 1
        i = self._index(path)
        if i is not None:
            self.rows[i].status = "Measuring failed"
            self.rows[i].error = message
            self._show(i)

    def _measure_finished(self, cancelled: bool) -> None:
        self._measure = None
        self._set_running(False)
        for i, r in enumerate(self.rows):
            if r.status.startswith(("Measuring…", "Waiting to be measured")):
                r.status = "Ready"
                self._show(i)
        if self._convert_after_measure and not cancelled:
            self._convert_after_measure = False
            self._start_converting()
        elif cancelled:
            self.summary.setText("Measuring cancelled.")

    # ------------------------------------------------------------------ converting

    def _ready_rows(self) -> list[int]:
        return [i for i, r in enumerate(self.rows) if r.todo]

    def _problems(self) -> list[tuple[int, str]]:
        out = []
        for i in self._ready_rows():
            r = self.rows[i]
            p = convert.audio_problem(r.info, self.settings_for(r))
            if p:
                out.append((i, p))
        return out

    def _refresh(self, *_) -> None:
        if self._busy():
            return
        ready = self._ready_rows()
        reading = sum(r.info is None and not r.error for r in self.rows)
        failed = sum(r.info is None and bool(r.error) for r in self.rows)
        missing_folder = self.chosen.isChecked() and not self.folder_edit.text().strip()
        converted = sum(r.info is not None and not r.todo for r in self.rows)
        problems = self._problems()
        unmeasured = self._unmeasured()
        parts = [f"{len(ready)} video{'s' * (len(ready) != 1)} to convert"]
        if ready:
            parts[0] += f" ({fmt_seconds(sum(self.rows[i].info.duration for i in ready))})"
        if converted:
            parts.append(f"{converted} already converted")
        if reading:
            parts.append(f"{reading} still being read")
        if failed:
            parts.append(f"{failed} cannot be read")
        if unmeasured:
            parts.append(f"{len(unmeasured)} will be measured first")
        if problems:
            parts.append(f"{len(problems)} with settings that do not fit (⚠ in the list)")
        if missing_folder:
            parts.append("choose the folder to save to")
        self.summary.setText(", ".join(parts) if self.rows else "Add videos to convert.")
        # the editor's problem line: for the videos it applies to
        if self.pro:
            shown = self._editing or [i for i in ready if self.rows[i].own is None]
            texts = {p for i, p in problems if i in shown}
            n = sum(1 for i, _ in problems if i in shown)
            self.editor.set_problem(f"{n} of {len(shown)} videos: " + " ".join(sorted(texts))
                                    if texts else "")
        else:
            self.editor.set_problem("")
        self.measure_button.setVisible(any(self.settings_for(r).measures for r in self.rows)
                                       or not self.rows and self.editor.settings().measures)
        self.measure_button.setEnabled(bool(unmeasured))
        self.start_button.setText(f"Convert {len(ready)}" if ready else "Convert")
        self.start_button.setEnabled(bool(ready) and not reading and not missing_folder
                                     and not problems
                                     and self.editor.codec.currentData() is not None
                                     and all(self.editor.codec_ok(self.settings_for(self.rows[i]).codec)
                                             for i in ready))

    def _start_or_cancel(self) -> None:
        if self._batch:
            self._batch.cancel()
            self.start_button.setEnabled(False)
            return
        if self._measure:
            self._convert_after_measure = False
            self._measure.cancel()
            self.start_button.setEnabled(False)
            return
        if not self._start_measuring(convert_after=True):
            self._start_converting()

    def _start_converting(self) -> None:
        rows = [i for i in self._ready_rows()
                if not self.settings_for(self.rows[i]).measures or self.measured(self.rows[i])]
        if not rows:
            self._refresh()
            return
        jobs = self._jobs_for(rows)
        items = convert.plan(jobs, self.output_folder())
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

    def _jobs_for(self, indices: list[int]) -> list[tuple]:
        pix = self._pix()
        out = []
        for i in indices:
            r = self.rows[i]
            cs = self.settings_for(r)
            m = self.measured(r)
            if cs.measures and m is None:
                out.append(None)
                continue
            out.append((convert.make_pro_job(r.info, r.frames, cs, m), pix.get(cs.codec)))
        return out

    def _set_running(self, running: bool) -> None:
        for w in (self.add_files_button, self.add_folder_button, self.remove_button,
                  self.clear_button, self.editor, self.easy_radio, self.pro_radio,
                  self.next_to, self.chosen, self.folder_edit, self.subfolders):
            w.setEnabled(not running)
        measuring = self._measure is not None
        self.measure_button.setText("Cancel measuring" if measuring else "Measure now")
        self.measure_button.setEnabled(measuring or not running)
        self.start_button.setText("Cancel" if running else "Convert")
        self.start_button.setEnabled(True)
        self._update_buttons()
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
            size = ""
            if r.output and r.output.exists() and row.info and row.info.size_bytes:
                size = f" ({r.output.stat().st_size / row.info.size_bytes * 100:.0f} %)"
            row.status, row.error, row.output = f"✔ {r.output.name}{size}", str(r.output), r.output
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
        if self._busy():
            if QMessageBox.question(self, "Convert videos",
                                    "A conversion is running. Cancel it and close?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            if self._batch:
                self._batch.cancel()
            if self._measure:
                self._measure.cancel()
        super().closeEvent(event)


def _wrap(layout) -> QWidget:
    w = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    w.setLayout(layout)
    return w
