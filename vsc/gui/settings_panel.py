# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Output settings of the selected clip, plus a live summary of what will happen.

Every edit is written straight into the clip's OutputSettings; afterwards all widgets are
re-synchronised from the settings, so dependent choices (containers, profiles, chroma …)
always match the chosen codec.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QSizePolicy, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..core import audio, formats, rife, smart
from ..core.encoders import EncoderStatus
from ..core.formats import COPY, CODECS
from ..core.job import KEYFRAME_TRIM_REASON, MODE_LABELS, Mode, _even
from ..i18n import N_, tr, trp
from .clips import (Clip, chroma_label, fmt_duration, fmt_rate, fmt_seconds, fmt_slowdown,
                    frame_rate_choices)

CUSTOM = "custom"
LOSSLESS, SMART, REENCODE = "lossless", "smart", "reencode"
AUDIO_TIP = N_("The original sound, stretched or compressed to the new length of the video.\n"
             "The pitch stays the same – no deep or squeaky voices. Very strong slow motion\n"
             "makes speech hard to understand (it is 10× slower), but it keeps its pitch.\n"
             "Phone slow-mo sound (stored lowered) is first brought back to its real pitch.")
PANEL_MIN_WIDTH = 330   # the form needs ~300 px (see CLAUDE.md) + the vertical scrollbar
SMART_DETAILS = N_("Smart re-encode joins copied and re-encoded parts only at keyframes: in / out "
                 "points snap to them,\nand sections marked “Re-encode” are widened to the "
                 "nearest ones – the extra frames are re-encoded\nat the speed they have "
                 "anyway.\n\n%s")
SPEED_PRESETS = [Fraction(1, n) for n in (2, 4, 5, 8, 10, 16, 20, 32)]
CHROMA_ORDER = {"411": 0, "420": 1, "422": 2, "444": 3}
RIFE_8BIT = N_("RIFE works on 8-bit RGB pictures: the extra precision of 10-bit / HDR footage "
             "is lost (risk of banding in gradients).")


def fill_combo(combo: QComboBox, items: list[tuple], current) -> None:
    """Set the items (text, data[, tooltip[, enabled]]) – only rebuilt if they changed."""
    items = [tuple(it) + (None, True)[len(it) - 2:] for it in items]
    old = [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]
    if old != [(t, d) for t, d, *_ in items]:
        combo.clear()
        for text, data, *_ in items:
            combo.addItem(text, data)
    model = combo.model()
    for i, (_, _, tip, enabled) in enumerate(items):
        combo.setItemData(i, tip, Qt.ToolTipRole)
        model.item(i).setEnabled(enabled)
    idx = combo.findData(current)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


def parse_fps(text: str) -> Fraction | None:
    try:
        r = Fraction(text.strip().replace(",", "."))
    except (ValueError, ZeroDivisionError):
        return None
    if r <= 0 or r > 1000:
        return None
    for _, preset in formats.FRAME_RATES:   # "23.976" means 24000/1001
        if abs(float(preset) - float(r)) < 0.0011:
            return preset
    return r


class SettingsPanel(QGroupBox):
    changed = Signal()       # the current clip's settings were edited
    easy_changed = Signal(bool)   # Easy / Pro switched (True = Easy)
    apply_to_all = Signal()

    def __init__(self, parent=None):
        super().__init__(tr("Output settings"), parent)
        self.clip: Clip | None = None
        self.encoders: dict[str, EncoderStatus] | None = None
        self.rife = None          # rife.RifeStatus once detected
        self._loading = False

        form_widget = QWidget()
        form = self.form = QFormLayout(form_widget)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # --- easy / pro: easy hides the codec details (codec, profile, preset, quality, chroma)
        self.easy_button = QRadioButton(tr("Easy"))
        self.easy_button.setToolTip(tr(
            "Fewer settings: no codec choice – smart re-encode uses the source codec,\n"
            "re-encode always AV1 (fast) – and the codec's default preset, quality and chroma."))
        self.pro_button = QRadioButton(tr("Pro"))
        self.pro_button.setToolTip(tr("All settings: codec, profile, preset, quality, chroma and bit depth."))
        self.level_group = QButtonGroup(self)
        self.level_group.addButton(self.easy_button)
        self.level_group.addButton(self.pro_button)
        self.easy = not _setting_bool("settings/pro", False)
        (self.easy_button if self.easy else self.pro_button).setChecked(True)
        self.level_group.buttonClicked.connect(self._level_clicked)
        form.addRow(tr("Settings:"), _row(self.easy_button, self.pro_button))

        # --- processing: lossless / smart / re-encode
        self.proc_lossless = QRadioButton(tr("Lossless"))
        self.proc_lossless.setToolTip(tr(
            "No re-encoding: every frame stays untouched, only its timing changes.\n"
            "Source codec and size, trim at keyframes. Fast and without any quality loss."))
        self.proc_smart = QRadioButton(tr("Smart re-encode"))
        self.proc_smart.setToolTip(tr(
            "Copies the clip and re-encodes only the speed sections you mark for it\n"
            "(Preview & trim tab), then joins everything into one file.\n"
            "Uses the source codec so the parts fit together; joins only at keyframes.\n"
            "Not playable on Apple devices."))
        self._smart_tip = self.proc_smart.toolTip()
        self.proc_reencode = QRadioButton(tr("Re-encode"))
        self.proc_reencode.setToolTip(tr("Re-encode the whole clip: any codec, size, speed and "
                                         "frame rate."))
        self.proc_group = QButtonGroup(self)
        for b in (self.proc_lossless, self.proc_smart, self.proc_reencode):
            self.proc_group.addButton(b)
        proc_box = QWidget()            # one below the other – fits a narrow panel
        proc_layout = QVBoxLayout(proc_box)
        proc_layout.setContentsMargins(0, 0, 0, 0)
        proc_layout.setSpacing(2)
        for b in (self.proc_lossless, self.proc_smart, self.proc_reencode):
            proc_layout.addWidget(b)
        form.addRow(tr("Processing:"), proc_box)

        # --- sound: one click to keep or leave it out
        self.audio_button = QPushButton()
        self.audio_button.setCheckable(True)
        self.audio_button.clicked.connect(self._edited)
        form.addRow(tr("Sound:"), _row(self.audio_button))

        # --- frame rate
        self.fps_combo = Combo()
        self.fps_combo.setToolTip(tr("Frame rate of the output file."))
        self.fps_edit = QLineEdit()
        self.fps_edit.setPlaceholderText(tr("e.g. 48 or 24000/1001"))
        self.fps_edit.setMaximumWidth(140)
        form.addRow(tr("Frame rate:"), _row(self.fps_combo, self.fps_edit, grow=self.fps_combo))
        self.original_info = QLabel()
        self.original_info.setWordWrap(True)
        form.addRow("", self.original_info)

        # --- speed
        self.speed_lossless = QRadioButton()
        self.speed_lossless.setToolTip(tr("Every source frame is used exactly once.\n"
                                          "Required for lossless retiming (mode A)."))
        self.speed_custom = QRadioButton(tr("Custom:"))
        group = QButtonGroup(self)
        group.addButton(self.speed_lossless)
        group.addButton(self.speed_custom)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setDecimals(5)
        self.speed_spin.setRange(0.0001, 100)
        self.speed_spin.setSingleStep(0.01)
        self.speed_spin.setSuffix(" ×")
        self.speed_spin.setToolTip(tr("Playback speed relative to real time (0.1 = 10× slower).\n"
                                      "Faster than the lossless speed → frames are skipped (B),\n"
                                      "slower → in-between frames are calculated (C)."))
        self.speed_presets = Combo()
        self.speed_presets.addItem(tr("Presets…"), None)
        for f in SPEED_PRESETS:
            self.speed_presets.addItem(tr("1/%d  (%d× slower)", f.denominator, f.denominator), str(f))
        self.speed_info = QLabel()
        self.speed_info.setWordWrap(True)
        form.addRow(tr("Speed:"), self.speed_lossless)
        form.addRow("", _row(self.speed_custom, self.speed_spin))
        form.addRow("", self.speed_presets)
        form.addRow("", self.speed_info)

        # --- codec
        self.codec_combo = Combo()
        self.container_combo = Combo()
        self.container_combo.setToolTip(tr("File format that holds the video stream."))
        self.codec_label = QLabel(tr("Codec:"))
        form.addRow(self.codec_label, self.codec_combo)
        form.addRow(tr("Container:"), self.container_combo)
        self.profile_combo = Combo()
        self.profile_label = QLabel(tr("Profile:"))
        form.addRow(self.profile_label, self.profile_combo)
        self.preset_combo = Combo()
        self.preset_combo.setToolTip(tr(formats.PRESET_TIP))
        self.preset_label = QLabel(tr("Preset:"))
        form.addRow(self.preset_label, self.preset_combo)
        self.quality_combo = Combo()
        self.quality_spin = QSpinBox()
        self.quality_spin.setToolTip(tr("The codec's own quality number"))
        self.quality_label = QLabel(tr("Quality:"))
        self.quality_row = _row(self.quality_combo, self.quality_spin, grow=self.quality_combo)
        form.addRow(self.quality_label, self.quality_row)
        self.chroma_combo = Combo()
        self.depth_combo = Combo()
        self.chroma_label = QLabel(tr("Chroma:"))
        self.depth_label = QLabel(tr("Bit depth:"))
        form.addRow(self.chroma_label, self.chroma_combo)
        form.addRow(self.depth_label, self.depth_combo)

        # --- size
        self.res_combo = Combo()
        self.res_combo.addItem(tr("Keep source size"), "source")
        for r in formats.RESOLUTIONS:
            self.res_combo.addItem(tr(r.label), r.key)
            self.res_combo.setItemData(self.res_combo.count() - 1, tr(r.tooltip), Qt.ToolTipRole)
        self.res_combo.addItem(tr("Custom…"), CUSTOM)
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(16, 16384)
            spin.setSingleStep(2)
        form.addRow(tr("Resolution:"), self.res_combo)
        form.addRow("", _row(self.width_spin, QLabel("×"), self.height_spin))
        self.aspect_combo = Combo()
        self.aspect_combo.addItem(tr("Keep original aspect (fit inside)"), "fit")
        self.aspect_combo.setItemData(0, tr("The picture keeps its proportions and is scaled to fit\n"
                                            "inside the chosen frame size."), Qt.ToolTipRole)
        self.aspect_combo.addItem(tr("Exactly this frame size"), "exact")
        for label, _ in formats.ASPECT_PRESETS:
            self.aspect_combo.addItem(tr("Aspect ratio %s", tr(label)), label)
        self.fit_combo = Combo()
        for key, (label, tip) in formats.FIT_MODES.items():
            self.fit_combo.addItem(tr(label), key)
            self.fit_combo.setItemData(self.fit_combo.count() - 1, tr(tip), Qt.ToolTipRole)
        form.addRow(tr("Aspect:"), self.aspect_combo)
        form.addRow(tr("Fit:"), self.fit_combo)
        self.scaler_combo = Combo()
        for s in formats.SCALERS:
            self.scaler_combo.addItem(tr("%s  (quality %d/5, speed %d/5)", tr(s.label), s.quality, s.speed),
                                      s.key)
            self.scaler_combo.setItemData(self.scaler_combo.count() - 1, tr(s.tooltip), Qt.ToolTipRole)
        form.addRow(tr("Scaling:"), self.scaler_combo)

        # --- interpolation
        self.interp_combo = Combo()
        form.addRow(tr("Interpolation:"), self.interp_combo)

        # --- summary + apply
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.apply_button = QPushButton(tr("Apply to all clips"))
        self.apply_button.setToolTip(tr("Copy these output settings to every clip in the list."))
        self.apply_button.clicked.connect(self.apply_to_all)

        scroll = self._scroll = QScrollArea()
        scroll.setMinimumWidth(PANEL_MIN_WIDTH)   # the splitter shrinks the preview instead
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(form_widget)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.summary)
        layout.addWidget(self.apply_button)

        for combo in (self.fps_combo, self.codec_combo, self.container_combo, self.profile_combo,
                      self.preset_combo, self.quality_combo, self.chroma_combo, self.depth_combo,
                      self.res_combo,
                      self.aspect_combo, self.fit_combo, self.scaler_combo, self.interp_combo):
            combo.currentIndexChanged.connect(self._edited)
        for spin in (self.speed_spin, self.quality_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._edited)
        self.fps_edit.editingFinished.connect(self._edited)
        self.speed_lossless.toggled.connect(self._edited)
        self.proc_group.buttonClicked.connect(self._edited)
        self.speed_presets.activated.connect(self._speed_preset)
        self.set_clip(None)

    # ------------------------------------------------------------------ public

    def set_clip(self, clip: Clip | None) -> None:
        self.clip = clip
        usable = bool(clip and clip.info)
        for child in self.findChildren(QWidget):
            if child is not self.summary:
                child.setEnabled(usable)
        self._sync()

    def refresh(self) -> None:
        """Re-read the clip, e.g. after its trim changed."""
        self._sync()

    def set_encoders(self, status: dict[str, EncoderStatus], rife_status=None) -> None:
        self.encoders = status
        self.rife = rife_status
        self._sync()

    # ------------------------------------------------------------------ widgets → settings

    def _speed_preset(self, index: int) -> None:
        value = self.speed_presets.itemData(index)
        self.speed_presets.setCurrentIndex(0)
        if value is None or not self.clip:
            return
        self.clip.settings.speed = Fraction(value)
        self._sync()
        self.changed.emit()

    def _edited(self, *_):
        if self._loading or not self.clip or not self.clip.info:
            return
        s, ui, info = self.clip.settings, self.clip.ui, self.clip.info

        fps = self.fps_combo.currentData()
        if fps == CUSTOM:
            fps = parse_fps(self.fps_edit.text()) or s.fps
            ui["fps"] = CUSTOM
        else:
            ui.pop("fps", None)
            fps = Fraction(fps)
        s.fps = fps

        if self.speed_lossless.isChecked():
            s.speed = None
        else:
            s.speed = Fraction(self.speed_spin.value()).limit_denominator(100000)

        process = self._chosen_process()
        codec = self.codec_combo.currentData() if process == REENCODE else s.codec
        if codec != s.codec:
            s.codec = codec
            s.container = s.profile = s.preset = s.quality = None  # codec defaults
            ui.pop("quality", None)                                  # other scale
        else:
            s.container = self.container_combo.currentData()
            s.profile = self.profile_combo.currentData()
            s.preset = self.preset_combo.currentData()
            c = formats.CODECS_BY_KEY.get(codec)
            level = self.quality_combo.currentData()
            if not (c and c.quality):
                s.quality = None
            elif level == CUSTOM:
                ui["quality"] = CUSTOM
                s.quality = self.quality_spin.value()
            else:
                ui.pop("quality", None)
                s.quality = int(level) if level is not None else None
            s.chroma = self.chroma_combo.currentData()
            s.depth = self.depth_combo.currentData()

        res = self.res_combo.currentData()
        if res != ui.get("res", "source") and res == CUSTOM:
            ui["w"], ui["h"] = info.display_size   # start from the source size
        elif res == CUSTOM:
            ui["w"], ui["h"] = self.width_spin.value(), self.height_spin.value()
        ui["res"] = res
        ui["aspect"] = self.aspect_combo.currentData()
        s.fit = self.fit_combo.currentData()
        s.scaler = self.scaler_combo.currentData()
        _apply_resolution(self.clip)

        interp = self.interp_combo.currentData()
        if interp:
            s.interpolation = interp
        if self.audio_button.isEnabled():
            s.audio = self.audio_button.isChecked()

        self._apply_process(process)

        self._sync()
        self.changed.emit()

    def _chosen_process(self) -> str:
        if self.proc_smart.isChecked():
            return SMART
        return REENCODE if self.proc_reencode.isChecked() else LOSSLESS

    def _apply_process(self, process: str) -> None:
        """Force the settings each processing mode requires."""
        clip = self.clip
        s, ui, info = clip.settings, clip.ui, clip.info
        if process == REENCODE:
            was_smart, s.smart = s.smart, False
            # coming from lossless or smart: AV1 fast, the default (user, v0.92); Easy: always
            if s.codec == COPY or was_smart or (self.easy and s.codec != self.default_codec()):
                s.codec = self.default_codec()
                s.container = s.profile = s.preset = s.quality = None
            if self.easy:
                force_easy(clip)
            return
        if process == LOSSLESS:
            if s.codec != COPY or s.smart:
                s.codec, s.smart = COPY, False
                s.container = s.profile = s.preset = s.quality = None
        else:  # SMART: the source codec, so that copied and re-encoded parts fit together
            key = smart.SMART_CODECS[info.codec][0]
            entering = not s.smart
            if not s.smart or s.codec != key:
                s.codec, s.smart = key, True
                s.container = s.profile = s.preset = s.quality = None
            s.chroma = s.depth = None
            if entering:
                preselect_smart_sections(clip)
            if self.easy:
                force_easy(clip)
        s.speed = None
        ui["res"] = "source"
        _apply_resolution(clip)
        if clip.frames:
            clip.trim = clip.job.snapped_trim()

    def default_codec(self) -> str:
        """AV1 fast (SVT-AV1) – x264 if this FFmpeg lacks it."""
        st = self.encoders.get("svtav1") if self.encoders else None
        return "svtav1" if st is None or st.available else "x264"

    def _level_clicked(self, *_):
        self.easy = self.easy_button.isChecked()
        QSettings().setValue("settings/pro", not self.easy)
        self.easy_changed.emit(self.easy)
        self._sync()

    def _process(self, clip: Clip) -> str:
        s = clip.settings
        if s.smart:
            return SMART
        return LOSSLESS if s.codec == COPY else REENCODE

    def set_process(self, process: str) -> None:
        """Choose a processing mode (as a click on its button would)."""
        {LOSSLESS: self.proc_lossless, SMART: self.proc_smart,
         REENCODE: self.proc_reencode}[process].setChecked(True)
        self._edited()

    # ------------------------------------------------------------------ settings → widgets

    def _sync(self) -> None:
        self._loading = True
        try:
            self._sync_widgets()
        finally:
            self._loading = False

    def _sync_widgets(self) -> None:
        clip = self.clip
        if not clip or not clip.info:
            self.summary.setText("")
            return
        s, ui, info = clip.settings, clip.ui, clip.info
        job = clip.job

        # processing mode
        process = self._process(clip)
        lossless_only = process == LOSSLESS
        {LOSSLESS: self.proc_lossless, SMART: self.proc_smart,
         REENCODE: self.proc_reencode}[process].setChecked(True)
        reason = smart.unavailable_reason(info)
        if reason is None and clip.joins is None:
            reason = tr("Analysing the keyframes of this clip …")
        elif reason is None and not clip.joins:
            reason = tr("No keyframe found where the parts could be joined.")
        self.proc_smart.setEnabled(reason is None or process == SMART)
        self.proc_smart.setToolTip(reason or self._smart_tip)

        # frame rate
        rates = frame_rate_choices(info.real_fps)
        custom_fps = ui.get("fps") == CUSTOM or s.fps not in [f for _, f in rates]
        fill_combo(self.fps_combo, self._fps_items(job, rates), CUSTOM if custom_fps else str(s.fps))
        self.original_info.setText(
            trp("Original: %d frame at %s fps = %s", "Original: %d frames at %s fps = %s",
                job.source_frame_count, job.source_frame_count, fmt_rate(info.real_fps),
                fmt_seconds(job.source_frame_count / float(info.real_fps)))
            + (tr(" (recorded slow-mo, the file plays at %s fps)", fmt_rate(info.fps))
               if info.slowmo_factor else ""))
        self.fps_edit.setVisible(custom_fps)
        if custom_fps and parse_fps(self.fps_edit.text()) != s.fps:
            self.fps_edit.setText(f"{s.fps.numerator}/{s.fps.denominator}"
                                  if s.fps.denominator != 1 else str(s.fps.numerator))

        # speed
        lossless = float(job.lossless_speed)
        self.speed_lossless.setText(tr("Lossless: %s× (%s)", f"{lossless:.4g}",
                                        fmt_slowdown(1 / lossless)))
        self.speed_lossless.setChecked(s.speed is None)
        self.speed_custom.setChecked(s.speed is not None)
        self.speed_spin.setEnabled(s.speed is not None)
        self.speed_spin.setValue(float(job.speed))
        sp = float(job.speed)
        if job.has_segments:
            mode = (tr("lossless, variable frame rate") if s.codec == COPY
                    else tr("re-encoded to a constant %s fps", fmt_rate(s.fps)))
            self.speed_info.setText(tr("<b>Output length %s</b> – speed sections (%s)",
                                       fmt_seconds(job.output_duration), mode))
        else:
            self.speed_info.setText(tr("<b>Output length %s</b> – %s than the original",
                                       fmt_seconds(job.output_duration), fmt_slowdown(1 / sp))
                                    if abs(sp - 1) > 1e-4 else
                                    tr("<b>Output length %s</b> – real time, like the original",
                                       fmt_seconds(job.output_duration)))

        # codec
        fill_combo(self.codec_combo, self._codec_items(), s.codec)
        codec = job.codec
        self.codec_combo.setToolTip(tr(codec.description) if codec else
                                    tr("Keeps the original video stream untouched; only the\n"
                                       "timestamps are changed. Fastest, no quality loss."))
        if process == SMART:
            containers = list(smart.CONTAINERS)
        elif codec is None:
            containers = formats.copy_containers(info.codec)
        else:
            containers = list(codec.containers)
        fill_combo(self.container_combo, [(c.upper(), c) for c in containers], job.container)

        profiles = codec.profiles if codec else ()
        fill_combo(self.profile_combo, [(tr(p.label), p.key, tr(p.tooltip)) for p in profiles],
                   job.profile.key if job.profile else None)
        presets = codec.presets if codec else ()
        fill_combo(self.preset_combo, [(formats.preset_label(codec, p), p) for p in presets],
                   s.preset or (codec.default_preset if codec else None))
        cineform = bool(codec) and codec.key == "cineform"
        self.preset_label.setText(tr("Compression:") if cineform else tr("Preset:"))
        self.preset_combo.setToolTip(tr(formats.CINEFORM_TIP if cineform else formats.PRESET_TIP))
        q = codec.quality if codec else None
        if q:
            self._sync_quality(clip, codec, q)
        pro = not self.easy
        for widget, visible in ((self.profile_combo, bool(profiles) and pro),
                                (self.preset_combo, bool(presets) and pro),
                                (self.quality_row, bool(q) and pro),
                                (self.codec_combo, pro),
                                (self.chroma_combo, pro),
                                (self.depth_combo, pro)):
            self.form.setRowVisible(widget, visible)

        self._sync_pixel_format(clip)

        # size
        res = ui.get("res", "source")
        self.res_combo.setCurrentIndex(self.res_combo.findData(res))
        resized = res != "source"
        for w in (self.width_spin, self.height_spin):
            w.setEnabled(res == CUSTOM)
        if res == CUSTOM:
            self.width_spin.setValue(ui.get("w", info.display_size[0]))
            self.height_spin.setValue(ui.get("h", info.display_size[1]))
        elif resized:
            r = next(r for r in formats.RESOLUTIONS if r.key == res)
            self.width_spin.setValue(r.width)
            self.height_spin.setValue(r.height)
        else:
            self.width_spin.setValue(info.display_size[0])
            self.height_spin.setValue(info.display_size[1])
        self.aspect_combo.setCurrentIndex(max(0, self.aspect_combo.findData(ui.get("aspect", "fit"))))
        self.fit_combo.setCurrentIndex(self.fit_combo.findData(s.fit))
        self.aspect_combo.setEnabled(resized)
        self.fit_combo.setEnabled(resized and ui.get("aspect", "fit") != "fit")
        self.scaler_combo.setCurrentIndex(self.scaler_combo.findData(s.scaler))
        self.scaler_combo.setEnabled(resized)

        # interpolation
        fill_combo(self.interp_combo, self._interp_items(), s.interpolation)
        interpolating = job.mode == Mode.INTERPOLATE
        self.interp_combo.setEnabled(interpolating)
        current = next(i for i in formats.INTERPOLATIONS if i.key == s.interpolation)
        self.interp_combo.setToolTip(tr(current.tooltip) if interpolating else
                                     tr("Only used when the speed is slower than the lossless speed."))

        # each processing mode enables only what it can use
        locked_size = (self.res_combo, self.width_spin, self.height_spin, self.aspect_combo,
                       self.fit_combo, self.scaler_combo)
        locked_speed = (self.speed_custom, self.speed_spin, self.speed_presets)
        if lossless_only:
            for w in (*locked_speed, *locked_size, self.codec_combo, self.profile_combo,
                      self.preset_combo, self.quality_combo, self.quality_spin, self.interp_combo):
                w.setEnabled(False)
        elif process == SMART:
            for w in (*locked_speed, *locked_size, self.codec_combo, self.profile_combo,
                      self.chroma_combo, self.depth_combo):
                w.setEnabled(False)
            for w in (self.preset_combo, self.quality_combo, self.quality_spin, self.interp_combo):
                w.setEnabled(True)
            self.codec_combo.setToolTip(tr("Smart re-encode always uses the source codec – "
                                           "otherwise the parts could not be joined."))
            self.interp_combo.setToolTip(tr("Used by re-encoded sections that play slower than "
                                            "their output frame rate."))
        else:
            for w in (self.speed_custom, self.speed_presets, self.codec_combo, self.profile_combo,
                      self.preset_combo, self.quality_combo, self.quality_spin, self.res_combo):
                w.setEnabled(True)

        # speed sections replace the global speed; lossless they keep every frame's own rate
        sections = job.has_segments and process != SMART
        self.speed_lossless.setEnabled(not sections)
        if sections:
            for w in (self.speed_custom, self.speed_spin, self.speed_presets):
                w.setEnabled(False)
        self.speed_info.setToolTip(tr("Speed sections (Preview & trim tab) set the speed of this clip.")
                                   if sections else "")
        copy_sections = sections and s.codec == COPY
        self.fps_combo.setEnabled(not copy_sections)
        self.fps_edit.setEnabled(not copy_sections)
        self.fps_combo.setToolTip(
            tr("Not used: without re-encoding every frame keeps its own duration (variable frame "
               "rate). Choose a codec to re-encode to one constant frame rate.")
            if copy_sections else
            tr("Constant frame rate of the output; each section is converted to it.")
            if sections else tr("Frame rate of the output file."))
        if process == SMART:
            for w in (self.speed_lossless, self.fps_combo, self.fps_edit):
                w.setEnabled(False)
            self.fps_combo.setToolTip(tr("Not used: copied parts keep their timing, re-encoded "
                                         "sections have their own output frame rate."))

        # sound
        reason = audio.unavailable_reason(job)
        on = s.audio and reason is None
        self.audio_button.setChecked(on)
        self.audio_button.setText(tr("🔊 Sound on – pitch preserved") if on else tr("🔇 Sound off"))
        self.audio_button.setEnabled(reason is None)
        self.audio_button.setToolTip(tr(reason) if reason else tr(AUDIO_TIP) + "\n\n"
                                     + (tr("Click to switch the sound off.") if on
                                        else tr("Click to switch the sound on.")))

        self.summary.setText(self._summary(clip))
        self.summary.setToolTip(tr(SMART_DETAILS, tr(smart.APPLE_WARNING))
                                if process == SMART else "")

    def _sync_quality(self, clip: Clip, codec, q) -> None:
        """Named levels with the codec's number in brackets; 'Custom…' shows the number box."""
        value = clip.settings.quality if clip.settings.quality is not None else q.default
        levels = formats.quality_levels(codec)
        custom = clip.ui.get("quality") == CUSTOM or value not in [v for _, _, v in levels]
        direction = tr("lower = better") if q.lower_is_better else tr("higher = better")
        qlabel = tr(q.label)
        items = [(tr("%s (%s %d)", tr(name), qlabel, v), str(v),
                  tr("%s\n\n%s %d (%s)", tr(tip), qlabel, v, direction))
                 for name, tip, v in levels]
        items.append((tr("Custom…"), CUSTOM, tr("Enter the %s value yourself (%d–%d, %s).",
                                                qlabel, q.minimum, q.maximum, direction)))
        fill_combo(self.quality_combo, items, CUSTOM if custom else str(value))
        self.quality_combo.setToolTip(tr(
            "How much detail is kept: the levels mean about the same for every codec.\n"
            "In brackets: this codec's own setting (%s, %s).\n"
            "One level down makes the file roughly 30–50 %% smaller.", qlabel, direction))
        self.quality_spin.setRange(q.minimum, q.maximum)
        self.quality_spin.setValue(value)
        self.quality_spin.setVisible(custom)
        self.quality_spin.setToolTip(f"{qlabel}: {tr(q.tooltip)}" if q.tooltip else qlabel)

    def _fps_items(self, job, rates: list[tuple[str, Fraction]]) -> list[tuple]:
        """Frame rates with the resulting slow-down and length when every frame is kept."""
        src, frames = job.info.real_fps, job.source_frame_count
        if job.has_segments:     # the sections decide the speed; this is only the output rate
            return [(label, str(fps), tr("Constant output frame rate")) for label, fps in rates] + [
                (tr("Custom…"), CUSTOM, tr("Enter any frame rate."))]
        items = []
        for label, fps in rates:
            length = fmt_seconds(frames / float(fps))
            slowdown = fmt_slowdown(float(src / fps))
            tip = trp("Every source frame shown once: %d frame at %s fps = %s, %s than the "
                      "original.\n(With a custom speed the length follows the speed instead.)",
                      "Every source frame shown once: %d frames at %s fps = %s, %s than the "
                      "original.\n(With a custom speed the length follows the speed instead.)",
                      frames, frames, fmt_rate(fps), length, slowdown)
            items.append((f"{label} – {slowdown}, {length}", str(fps), tip))
        items.append((tr("Custom…"), CUSTOM, tr("Enter any frame rate.")))
        return items

    def _interp_items(self) -> list[tuple]:
        items = []
        for i in formats.INTERPOLATIONS:
            label, tip, enabled = tr("%s  (quality %d/5)", tr(i.label), i.quality), tr(i.tooltip), True
            job = self.clip.job if self.clip and self.clip.info else None
            if i.needs_gpu and job and job.has_segments:
                label += "  " + tr("(not with speed sections)")
                tip, enabled = tip + "\n\n" + tr("RIFE cannot be combined with speed sections."), False
            elif i.needs_gpu and job and job.codec and job.codec.external:
                label += "  " + tr("(not with AV2)")
                tip, enabled = tip + "\n\n" + tr("RIFE cannot be combined with AV2."), False
            elif i.needs_gpu:
                r = self.rife
                if r is None:
                    tip, enabled = tip + "\n\n" + tr("Checking for a Vulkan GPU…"), False
                elif not r.available:
                    label += "  " + tr("(unavailable)")
                    tip, enabled = tip + "\n\n" + tr("Not available: %s", tr(r.reason)), False
                elif r.software:
                    label += "  " + tr("(no GPU – very slow)")
                    tip += "\n\n" + tr("Only a software Vulkan device was found (%s).\n"
                                         "RIFE runs on the CPU and is extremely slow.", r.gpu)
                else:
                    tip += "\n\n" + tr("Runs on: %s", r.gpu)
            items.append((label, i.key, tip, enabled))
        return items

    def _codec_items(self) -> list[tuple]:
        items = [(tr("Keep source codec – lossless retime"), COPY,
                  tr("Choose “Lossless” under Processing to keep the source stream."), False)]
        groups = ((tr("Lossless"), lambda c: c.lossless),
                  (tr("Lossy"), lambda c: not c.lossless and not c.hw),
                  (tr("Hardware"), lambda c: c.hw))
        for group, match in groups:
            for c in CODECS:
                if not match(c):
                    continue
                st = self.encoders.get(c.key) if self.encoders else None
                label, desc = f"{group}: {tr(c.label)}", tr(c.description)
                if self.encoders is None:
                    items.append((label, c.key, tr("Detecting encoders…"), False))
                elif st and st.available:
                    items.append((label, c.key, desc, True))
                else:
                    reason = tr(st.reason) if st else tr("unknown")
                    items.append((label + "  " + tr("(unavailable)"), c.key,
                                  desc + "\n\n" + tr("Not available: %s", reason), False))
        return items

    def _smart_summary(self, clip: Clip) -> list[str]:
        job = clip.job
        if clip.joins is None:
            return [tr("Analysing the keyframes of this clip …")]
        parts = job.smart_parts()
        encoded = [p for p in parts if p.kind == "encode"]
        lines = [tr("Codec: %s – the source codec, so the parts fit together.",
                    tr(job.codec.label))]
        if not encoded:
            lines.append(tr("No section is marked “Re-encode” (Preview & trim tab) – the whole "
                            "clip is copied."))
        else:
            n_copy = sum(p.frames for p in parts if p.kind == "copy")
            n_enc = sum(p.frames for p in encoded)
            lines.append(trp("%d part", "%d parts", len(parts), len(parts)) + ": "
                         + trp("%d frame copied", "%d frames copied", n_copy, n_copy) + ", "
                         + trp("%d frame re-encoded in %d part(s).",
                               "%d frames re-encoded in %d part(s).", n_enc, n_enc, len(encoded)))
        lines.append(trp("Joins only at keyframes (every %d frame).",
                         "Joins only at keyframes (every %d frames).",
                         _key_interval(job.frames), _key_interval(job.frames)))
        lines.append("<span style='color:#d35400'>" + tr("⚠ Does not play on Apple devices "
                     "(hover for details).") + "</span>")
        lines.append(trp("%d → %d frame, %s", "%d → %d frames, %s", job.output_frame_count,
                         job.source_frame_count, job.output_frame_count,
                         fmt_duration(job.output_duration)))
        lines.append(_sound_line(job))
        ext = formats.CONTAINER_EXT[job.container]
        lines.append(tr("File: %s", f"{job.default_output_name()}{ext}"))
        return lines

    def supported_pix_fmts(self, clip: Clip) -> list[str] | None:
        codec = clip.job.codec
        if codec and self.encoders and codec.key in self.encoders:
            return self.encoders[codec.key].pix_fmts or None
        return None

    def _sync_pixel_format(self, clip: Clip) -> None:
        job, s, info = clip.job, clip.settings, clip.info
        codec = job.codec
        if codec is None:
            src = tr("Source (%s)", chroma_label(info.chroma))
            fill_combo(self.chroma_combo, [(src, None)], None)
            fill_combo(self.depth_combo, [(tr("Source (%d-bit)", info.bit_depth), None)], None)
            for w in (self.chroma_combo, self.depth_combo):
                w.setEnabled(False)
                w.setToolTip(tr("Lossless retime keeps the source format."))
            return
        allowed = formats.allowed_formats(codec, job.profile, self.supported_pix_fmts(clip))
        chromas = sorted({c for c, _ in allowed}, key=CHROMA_ORDER.get)
        depths = sorted({d for _, d in allowed})
        src_rank = CHROMA_ORDER.get(info.chroma, 3)
        chroma_items = [(tr("Like source (%s)", chroma_label(info.chroma)), None,
                         tr("Keep the source subsampling if the codec supports it."))]
        for c in chromas:
            label, tip = formats.CHROMA[c]
            tip = tr(tip)
            if CHROMA_ORDER[c] > src_rank:
                tip += "\n\n" + tr(formats.CHROMA_UPSAMPLE_NOTE)
            chroma_items.append((label, c, tip))
        depth_items = [(tr("Like source (%d-bit)", info.bit_depth), None,
                        tr("Keep the source bit depth (8 or 10-bit) if the codec supports it."))]
        depth_items += [(tr(formats.DEPTHS[d][0]), d, tr(formats.DEPTHS[d][1])) for d in depths]
        fill_combo(self.chroma_combo, chroma_items, s.chroma)
        fill_combo(self.depth_combo, depth_items, s.depth)
        for w in (self.chroma_combo, self.depth_combo):
            w.setEnabled(True)
        self.chroma_combo.setToolTip(tr(self.chroma_combo.currentData() and
                                        formats.CHROMA[self.chroma_combo.currentData()][1] or
                                        "Chroma subsampling – how much colour detail is stored."))
        self.depth_combo.setToolTip(tr("Bit depth – number of brightness / colour steps."))

    def _summary(self, clip: Clip) -> str:
        job = clip.job
        lines = [f"<b>{tr(MODE_LABELS[job.mode])}</b>"]
        if job.mode == Mode.SMART:
            return "<br>".join(lines + self._smart_summary(clip))
        if job.has_segments:
            n = sum(1 for g in job.segments if g.start < job.trim_end and g.end > job.trim.start)
            if job.mode == Mode.RETIME:
                lines.append(trp("%d speed section, rest in real time – every frame keeps its "
                                 "own duration (variable frame rate). Plays in all common players; "
                                 "editing programs prefer a constant frame rate (choose a codec).",
                                 "%d speed sections, rest in real time – every frame keeps its "
                                 "own duration (variable frame rate). Plays in all common players; "
                                 "editing programs prefer a constant frame rate (choose a codec).",
                                 n, n))
                fastest = max(p.rate for p in job.pieces())
                if fastest > clip.info.real_fps:
                    lines.append(
                        "<span style='color:#d35400'>" + tr(
                            "Fast sections keep every frame: a player "
                            "has to decode %s frames per second there, which most "
                            "computers can't – it will stutter. For smooth playback choose a codec: "
                            "the constant frame rate then skips the extra frames.",
                            fmt_rate(fastest)) + "</span>")
            else:
                lines.append(trp("%d speed section, rest in real time – re-encoded to a "
                                 "constant %s fps.",
                                 "%d speed sections, rest in real time – re-encoded to a "
                                 "constant %s fps.", n, n, fmt_rate(job.settings.fps)))
                if rife.MODELS and job.settings.interpolation in rife.MODELS:
                    lines.append("<span style='color:#c0392b'>" + tr(
                        "RIFE cannot be combined with speed sections – choose another "
                        "interpolation.") + "</span>")
        if (job.codec and job.codec.external and job.mode == Mode.INTERPOLATE
                and job.settings.interpolation in rife.MODELS):
            lines.append("<span style='color:#c0392b'>" + tr(
                "RIFE cannot be combined with AV2 – choose another interpolation.") + "</span>")
        if job.codec and job.codec.external:
            lines.append("<span style='color:#d35400'>" + tr(
                "AV2 reference encoder: ~75 s per 1080p frame – test encodes use at most "
                "5 frames.") + "</span>")
        if rife.is_rife(job) and (clip.info.bit_depth > 8 or clip.info.is_hdr):
            lines.append(f"<span style='color:#d35400'>{tr(RIFE_8BIT)}</span>")
        if job.mode == Mode.RETIME:
            blockers = job.retime_blockers()
            if blockers:
                lines.append("<span style='color:#c0392b'>"
                             + tr("Lossless retime is not possible:") + "<br>• "
                             + "<br>• ".join(tr(b) for b in blockers)
                             + "<br>" + tr("Choose “lossless speed”, keep the source size, "
                                           "or pick a codec to re-encode.") + "</span>")
            else:
                lines.append(tr("Trimming is only possible at keyframes.")
                             + f" <span title='{tr(KEYFRAME_TRIM_REASON)}'>{tr('(why?)')}</span>")
        rate = (tr("variable frame rate") if job.has_segments and job.mode == Mode.RETIME
                else tr("%s fps", f"{float(job.settings.fps):.5g}"))
        lines.append(trp("%d → %d frame, %s at %s", "%d → %d frames, %s at %s",
                         job.output_frame_count, job.source_frame_count, job.output_frame_count,
                         fmt_duration(job.output_duration), rate))
        if job.codec:
            w, h = job.output_size()
            try:
                chroma, depth, pix = job.output_format(self.supported_pix_fmts(clip))
                fmt = f"{chroma_label(chroma)} {depth}-bit ({pix})"
            except ValueError as e:
                fmt = f"<span style='color:#c0392b'>{e}</span>"
            lines.append(f"{w}×{h}, {fmt}")
        else:
            w, h = clip.info.display_size
            lines.append(f"{w}×{h}, " + tr("%s (unchanged)", clip.info.pix_fmt))
        lines.append(_sound_line(job))
        ext = formats.CONTAINER_EXT[job.container]
        lines.append(tr("File: %s", f"{job.default_output_name()}{ext}"))
        return "<br>".join(lines)


def _sound_line(job) -> str:
    if not audio.wanted(job):
        return tr("Sound: none") + ("" if job.info.has_audio else tr(" (the clip has none)"))
    restored = tr(" – phone slow-mo sound back at its real pitch") \
        if audio.slowmo_factor(job) > 1.001 else ""
    if job.has_segments or job.settings.smart:
        return tr("Sound: follows the speed sections, pitch preserved") + restored
    real = sum(b - a for a, b, _ in audio.pieces(job))
    factor = job.output_duration / real if real > 0 else 1
    change = (tr("unchanged length") if abs(factor - 1) < 1e-3 else
              tr("%s× longer", f"{factor:.3g}") if factor > 1 else
              tr("%s× shorter", f"{1 / factor:.3g}"))
    return tr("Sound: %s, pitch preserved", change) + restored


def _key_interval(frames) -> int:
    gaps = sorted(b - a for a, b in zip(frames.keyframes, frames.keyframes[1:]))
    return gaps[len(gaps) // 2] if gaps else frames.count


def _apply_resolution(clip: Clip) -> None:
    """Translate the resolution / aspect choice in clip.ui into OutputSettings."""
    s, ui = clip.settings, clip.ui
    res = ui.get("res", "source")
    if res == "source":
        s.resize, s.width, s.height = "source", None, None
        return
    if res == CUSTOM:
        w, h = ui["w"], ui["h"]
    else:
        r = next(r for r in formats.RESOLUTIONS if r.key == res)
        w, h = r.width, r.height
    aspect = ui.get("aspect", "fit")
    if aspect == "fit":
        s.resize = "fit_box"
    elif aspect == "exact":
        s.resize = "exact"
    else:
        ratio = dict(formats.ASPECT_PRESETS)[aspect]
        s.resize = "exact"
        h = _even(w / ratio)
    s.width, s.height = w, h


def _setting_bool(key: str, default: bool) -> bool:
    value = QSettings().value(key, default)
    return value in (True, "true", "1", 1)


def force_easy(clip: Clip) -> None:
    """Easy settings: the codec's default preset, quality and profile, chroma / depth like the
    source (re-encode: the codec itself is AV1 fast – set by the caller)."""
    s = clip.settings
    if s.codec == COPY:
        return
    s.profile = s.preset = s.quality = None
    s.chroma = s.depth = None
    clip.ui.pop("quality", None)


def preselect_smart_sections(clip: Clip) -> None:
    """Smart re-encode chosen: every section whose playing rate differs from its output frame
    rate is marked for re-encoding, the others are copied (user, v0.92 – like Android)."""
    from .timeline import default_out_fps
    new = []
    for g in clip.segments:
        out = g.out_fps or default_out_fps()
        new.append(replace(g, reencode=g.fps != out, out_fps=out))
    clip.edit_segments(new, "smart re-encode: mark sections that differ from their output rate")


def _row(*widgets, grow: QWidget | None = None) -> QWidget:
    """Widgets side by side; `grow` takes the free width (else it stays on the right)."""
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget, 1 if widget is grow else 0)
    if grow is None:
        layout.addStretch(1)
    return w


class Combo(QComboBox):
    """Shrinks with a narrow panel (long texts are cut off); the open list shows them in full."""

    def __init__(self, chars: int = 12):
        super().__init__()
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(chars)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def showPopup(self) -> None:
        view = self.view()
        wanted = view.sizeHintForColumn(0) + view.verticalScrollBar().sizeHint().width() + 12
        screen = self.screen().availableGeometry().width() if self.screen() else 1200
        view.setMinimumWidth(min(max(wanted, self.width()), screen // 2))
        super().showPopup()
