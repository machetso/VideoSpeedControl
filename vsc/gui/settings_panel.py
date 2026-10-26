"""Output settings of the selected clip, plus a live summary of what will happen.

Every edit is written straight into the clip's OutputSettings; afterwards all widgets are
re-synchronised from the settings, so dependent choices (containers, profiles, chroma …)
always match the chosen codec.
"""
from __future__ import annotations

from fractions import Fraction

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..core import formats, rife, smart
from ..core.encoders import EncoderStatus
from ..core.formats import COPY, CODECS
from ..core.job import KEYFRAME_TRIM_REASON, MODE_LABELS, Mode, _even
from .clips import (Clip, chroma_label, fmt_duration, fmt_rate, fmt_seconds, fmt_slowdown,
                    frame_rate_choices)

CUSTOM = "custom"
LOSSLESS, SMART, REENCODE = "lossless", "smart", "reencode"
SPEED_PRESETS = [Fraction(1, n) for n in (2, 4, 5, 8, 10, 16, 20, 32)]
CHROMA_ORDER = {"411": 0, "420": 1, "422": 2, "444": 3}
RIFE_8BIT = ("RIFE works on 8-bit RGB pictures: the extra precision of 10-bit / HDR footage "
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
    apply_to_all = Signal()

    def __init__(self, parent=None):
        super().__init__("Output settings", parent)
        self.clip: Clip | None = None
        self.encoders: dict[str, EncoderStatus] | None = None
        self.rife = None          # rife.RifeStatus once detected
        self._loading = False

        form_widget = QWidget()
        form = self.form = QFormLayout(form_widget)

        # --- processing: lossless / smart / re-encode
        self.proc_lossless = QRadioButton("Lossless")
        self.proc_lossless.setToolTip(
            "No re-encoding: every frame stays untouched, only its timing changes.\n"
            "Source codec and size, trim at keyframes. Fast and without any quality loss.")
        self.proc_smart = QRadioButton("Smart re-encode")
        self.proc_smart.setToolTip(
            "Copies the clip and re-encodes only the speed sections you mark for it\n"
            "(Preview & trim tab), then joins everything into one file.\n"
            "Uses the source codec so the parts fit together; joins only at keyframes.\n"
            "Not playable on Apple devices.")
        self._smart_tip = self.proc_smart.toolTip()
        self.proc_reencode = QRadioButton("Re-encode")
        self.proc_reencode.setToolTip("Re-encode the whole clip: any codec, size, speed and "
                                      "frame rate.")
        self.proc_group = QButtonGroup(self)
        for b in (self.proc_lossless, self.proc_smart, self.proc_reencode):
            self.proc_group.addButton(b)
        form.addRow("Processing:", _row(self.proc_lossless, self.proc_smart, self.proc_reencode))

        # --- frame rate
        self.fps_combo = QComboBox()
        self.fps_combo.setToolTip("Frame rate of the output file.")
        self.fps_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.fps_edit = QLineEdit()
        self.fps_edit.setPlaceholderText("e.g. 48 or 24000/1001")
        self.fps_edit.setMaximumWidth(140)
        form.addRow("Frame rate:", _row(self.fps_combo, self.fps_edit))
        self.original_info = QLabel()
        form.addRow("", self.original_info)

        # --- speed
        self.speed_lossless = QRadioButton()
        self.speed_lossless.setToolTip("Every source frame is used exactly once.\n"
                                       "Required for lossless retiming (mode A).")
        self.speed_custom = QRadioButton("Custom:")
        group = QButtonGroup(self)
        group.addButton(self.speed_lossless)
        group.addButton(self.speed_custom)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setDecimals(5)
        self.speed_spin.setRange(0.0001, 100)
        self.speed_spin.setSingleStep(0.01)
        self.speed_spin.setSuffix(" ×")
        self.speed_spin.setToolTip("Playback speed relative to real time (0.1 = 10× slower).\n"
                                   "Faster than the lossless speed → frames are skipped (B),\n"
                                   "slower → in-between frames are calculated (C).")
        self.speed_presets = QComboBox()
        self.speed_presets.addItem("Presets…", None)
        for f in SPEED_PRESETS:
            self.speed_presets.addItem(f"1/{f.denominator}  ({f.denominator}× slower)", str(f))
        self.speed_info = QLabel()
        form.addRow("Speed:", self.speed_lossless)
        form.addRow("", _row(self.speed_custom, self.speed_spin, self.speed_presets))
        form.addRow("", self.speed_info)

        # --- codec
        self.codec_combo = QComboBox()
        self.container_combo = QComboBox()
        self.container_combo.setToolTip("File format that holds the video stream.")
        form.addRow("Codec:", self.codec_combo)
        form.addRow("Container:", self.container_combo)
        self.profile_combo = QComboBox()
        self.profile_label = QLabel("Profile:")
        form.addRow(self.profile_label, self.profile_combo)
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip("Encoder speed / efficiency trade-off.\n"
                                     "Slower presets give smaller files at the same quality.")
        self.preset_label = QLabel("Preset:")
        form.addRow(self.preset_label, self.preset_combo)
        self.quality_spin = QSpinBox()
        self.quality_label = QLabel("Quality:")
        form.addRow(self.quality_label, self.quality_spin)
        self.chroma_combo = QComboBox()
        self.depth_combo = QComboBox()
        for combo in (self.chroma_combo, self.depth_combo):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        form.addRow("Chroma / depth:", _row(self.chroma_combo, self.depth_combo))

        # --- size
        self.res_combo = QComboBox()
        self.res_combo.addItem("Keep source size", "source")
        for r in formats.RESOLUTIONS:
            self.res_combo.addItem(r.label, r.key)
            self.res_combo.setItemData(self.res_combo.count() - 1, r.tooltip, Qt.ToolTipRole)
        self.res_combo.addItem("Custom…", CUSTOM)
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(16, 16384)
            spin.setSingleStep(2)
        form.addRow("Resolution:", self.res_combo)
        form.addRow("", _row(self.width_spin, QLabel("×"), self.height_spin))
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItem("Keep original aspect (fit inside)", "fit")
        self.aspect_combo.setItemData(0, "The picture keeps its proportions and is scaled to fit\n"
                                         "inside the chosen frame size.", Qt.ToolTipRole)
        self.aspect_combo.addItem("Exactly this frame size", "exact")
        for label, _ in formats.ASPECT_PRESETS:
            self.aspect_combo.addItem(f"Aspect ratio {label}", label)
        self.fit_combo = QComboBox()
        for key, (label, tip) in formats.FIT_MODES.items():
            self.fit_combo.addItem(label, key)
            self.fit_combo.setItemData(self.fit_combo.count() - 1, tip, Qt.ToolTipRole)
        form.addRow("Aspect:", _row(self.aspect_combo, self.fit_combo))
        self.scaler_combo = QComboBox()
        for s in formats.SCALERS:
            self.scaler_combo.addItem(f"{s.label}  (quality {s.quality}/5, speed {s.speed}/5)",
                                      s.key)
            self.scaler_combo.setItemData(self.scaler_combo.count() - 1, s.tooltip, Qt.ToolTipRole)
        form.addRow("Scaling:", self.scaler_combo)

        # --- interpolation
        self.interp_combo = QComboBox()
        form.addRow("Interpolation:", self.interp_combo)

        # --- summary + apply
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.apply_button = QPushButton("Apply to all clips")
        self.apply_button.setToolTip("Copy these output settings to every clip in the list.")
        self.apply_button.clicked.connect(self.apply_to_all)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(form_widget)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.summary)
        layout.addWidget(self.apply_button)

        for combo in (self.fps_combo, self.codec_combo, self.container_combo, self.profile_combo,
                      self.preset_combo, self.chroma_combo, self.depth_combo, self.res_combo,
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
        else:
            s.container = self.container_combo.currentData()
            s.profile = self.profile_combo.currentData()
            s.preset = self.preset_combo.currentData()
            c = formats.CODECS_BY_KEY.get(codec)
            s.quality = self.quality_spin.value() if c and c.quality else None
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
            s.smart = False
            if s.codec == COPY:
                s.codec = "x264"
                s.container = s.profile = s.preset = s.quality = None
            return
        if process == LOSSLESS:
            if s.codec != COPY or s.smart:
                s.codec, s.smart = COPY, False
                s.container = s.profile = s.preset = s.quality = None
        else:  # SMART: the source codec, so that copied and re-encoded parts fit together
            key = smart.SMART_CODECS[info.codec][0]
            if not s.smart or s.codec != key:
                s.codec, s.smart = key, True
                s.container = s.profile = s.preset = s.quality = None
            s.chroma = s.depth = None
        s.speed = None
        ui["res"] = "source"
        _apply_resolution(clip)
        if clip.frames:
            clip.trim = clip.job.snapped_trim()

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
            reason = "Analysing the keyframes of this clip …"
        elif reason is None and not clip.joins:
            reason = "No keyframe found where the parts could be joined."
        self.proc_smart.setEnabled(reason is None or process == SMART)
        self.proc_smart.setToolTip(reason or self._smart_tip)

        # frame rate
        rates = frame_rate_choices(info.real_fps)
        custom_fps = ui.get("fps") == CUSTOM or s.fps not in [f for _, f in rates]
        fill_combo(self.fps_combo, self._fps_items(job, rates), CUSTOM if custom_fps else str(s.fps))
        self.original_info.setText(
            f"Original: {job.source_frame_count} frames at {fmt_rate(info.real_fps)} fps = "
            f"{fmt_seconds(job.source_frame_count / float(info.real_fps))}"
            + (f" (recorded slow-mo, the file plays at {fmt_rate(info.fps)} fps)"
               if info.slowmo_factor else ""))
        self.fps_edit.setVisible(custom_fps)
        if custom_fps and parse_fps(self.fps_edit.text()) != s.fps:
            self.fps_edit.setText(f"{s.fps.numerator}/{s.fps.denominator}"
                                  if s.fps.denominator != 1 else str(s.fps.numerator))

        # speed
        lossless = float(job.lossless_speed)
        self.speed_lossless.setText(f"Lossless speed: {lossless:.5g}×  "
                                    f"({fmt_slowdown(1 / lossless)})")
        self.speed_lossless.setChecked(s.speed is None)
        self.speed_custom.setChecked(s.speed is not None)
        self.speed_spin.setEnabled(s.speed is not None)
        self.speed_spin.setValue(float(job.speed))
        sp = float(job.speed)
        if job.has_segments:
            mode = ("lossless, variable frame rate" if s.codec == COPY
                    else f"re-encoded to a constant {fmt_rate(s.fps)} fps")
            self.speed_info.setText(f"<b>Output length {fmt_seconds(job.output_duration)}</b> – "
                                    f"speed sections ({mode})")
        else:
            self.speed_info.setText(f"<b>Output length {fmt_seconds(job.output_duration)}</b> – "
                                    f"{fmt_slowdown(1 / sp)} than the original" if abs(sp - 1) > 1e-4
                                    else f"<b>Output length {fmt_seconds(job.output_duration)}</b> – "
                                         "real time, like the original")

        # codec
        fill_combo(self.codec_combo, self._codec_items(), s.codec)
        codec = job.codec
        self.codec_combo.setToolTip(codec.description if codec else
                                    "Keeps the original video stream untouched; only the\n"
                                    "timestamps are changed. Fastest, no quality loss.")
        if process == SMART:
            containers = list(smart.CONTAINERS)
        elif codec is None:
            containers = formats.copy_containers(info.codec)
        else:
            containers = list(codec.containers)
        fill_combo(self.container_combo, [(c.upper(), c) for c in containers], job.container)

        profiles = codec.profiles if codec else ()
        fill_combo(self.profile_combo, [(p.label, p.key, p.tooltip) for p in profiles],
                   job.profile.key if job.profile else None)
        presets = codec.presets if codec else ()
        fill_combo(self.preset_combo, [(p, p) for p in presets],
                   s.preset or (codec.default_preset if codec else None))
        q = codec.quality if codec else None
        if q:
            self.quality_spin.setRange(q.minimum, q.maximum)
            self.quality_spin.setValue(s.quality if s.quality is not None else q.default)
            self.quality_spin.setToolTip(q.tooltip)
            self.quality_label.setText(q.label + ":")
        for widget, visible in ((self.profile_combo, bool(profiles)),
                                (self.preset_combo, bool(presets)),
                                (self.quality_spin, bool(q))):
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
        self.interp_combo.setToolTip(current.tooltip if interpolating else
                                     "Only used when the speed is slower than the lossless speed.")

        # each processing mode enables only what it can use
        locked_size = (self.res_combo, self.width_spin, self.height_spin, self.aspect_combo,
                       self.fit_combo, self.scaler_combo)
        locked_speed = (self.speed_custom, self.speed_spin, self.speed_presets)
        if lossless_only:
            for w in (*locked_speed, *locked_size, self.codec_combo, self.profile_combo,
                      self.preset_combo, self.quality_spin, self.interp_combo):
                w.setEnabled(False)
        elif process == SMART:
            for w in (*locked_speed, *locked_size, self.codec_combo, self.profile_combo,
                      self.chroma_combo, self.depth_combo):
                w.setEnabled(False)
            for w in (self.preset_combo, self.quality_spin, self.interp_combo):
                w.setEnabled(True)
            self.codec_combo.setToolTip("Smart re-encode always uses the source codec – "
                                        "otherwise the parts could not be joined.")
            self.interp_combo.setToolTip("Used by re-encoded sections that play slower than "
                                         "their output frame rate.")
        else:
            for w in (self.speed_custom, self.speed_presets, self.codec_combo, self.profile_combo,
                      self.preset_combo, self.quality_spin, self.res_combo):
                w.setEnabled(True)

        # speed sections replace the global speed; lossless they keep every frame's own rate
        sections = job.has_segments and process != SMART
        self.speed_lossless.setEnabled(not sections)
        if sections:
            for w in (self.speed_custom, self.speed_spin, self.speed_presets):
                w.setEnabled(False)
        self.speed_info.setToolTip("Speed sections (Preview & trim tab) set the speed of this clip."
                                   if sections else "")
        copy_sections = sections and s.codec == COPY
        self.fps_combo.setEnabled(not copy_sections)
        self.fps_edit.setEnabled(not copy_sections)
        self.fps_combo.setToolTip(
            "Not used: without re-encoding every frame keeps its own duration (variable frame "
            "rate). Choose a codec to re-encode to one constant frame rate."
            if copy_sections else
            "Constant frame rate of the output; each section is converted to it."
            if sections else "Frame rate of the output file.")
        if process == SMART:
            for w in (self.speed_lossless, self.fps_combo, self.fps_edit):
                w.setEnabled(False)
            self.fps_combo.setToolTip("Not used: copied parts keep their timing, re-encoded "
                                      "sections have their own output frame rate.")

        self.summary.setText(self._summary(clip))

    def _fps_items(self, job, rates: list[tuple[str, Fraction]]) -> list[tuple]:
        """Frame rates with the resulting slow-down and length when every frame is kept."""
        src, frames = job.info.real_fps, job.source_frame_count
        if job.has_segments:     # the sections decide the speed; this is only the output rate
            return [(label, str(fps), "Constant output frame rate") for label, fps in rates] + [
                ("Custom…", CUSTOM, "Enter any frame rate.")]
        items = []
        for label, fps in rates:
            length = fmt_seconds(frames / float(fps))
            slowdown = fmt_slowdown(float(src / fps))
            tip = (f"Every source frame shown once: {frames} frames at {fmt_rate(fps)} fps = "
                   f"{length}, {slowdown} than the original.\n"
                   "(With a custom speed the length follows the speed instead.)")
            items.append((f"{label} – {slowdown}, {length}", str(fps), tip))
        items.append(("Custom…", CUSTOM, "Enter any frame rate."))
        return items

    def _interp_items(self) -> list[tuple]:
        items = []
        for i in formats.INTERPOLATIONS:
            label, tip, enabled = f"{i.label}  (quality {i.quality}/5)", i.tooltip, True
            job = self.clip.job if self.clip and self.clip.info else None
            if i.needs_gpu and job and job.has_segments:
                label += "  (not with speed sections)"
                tip, enabled = tip + "\n\nRIFE cannot be combined with speed sections.", False
            elif i.needs_gpu and job and job.codec and job.codec.external:
                label += "  (not with AV2)"
                tip, enabled = tip + "\n\nRIFE cannot be combined with AV2.", False
            elif i.needs_gpu:
                r = self.rife
                if r is None:
                    tip, enabled = tip + "\n\nChecking for a Vulkan GPU…", False
                elif not r.available:
                    label += "  (unavailable)"
                    tip, enabled = tip + f"\n\nNot available: {r.reason}", False
                elif r.software:
                    label += "  (no GPU – very slow)"
                    tip += (f"\n\nOnly a software Vulkan device was found ({r.gpu}).\n"
                            "RIFE runs on the CPU and is extremely slow.")
                else:
                    tip += f"\n\nRuns on: {r.gpu}"
            items.append((label, i.key, tip, enabled))
        return items

    def _codec_items(self) -> list[tuple]:
        items = [("Keep source codec – lossless retime", COPY,
                  "Choose “Lossless” under Processing to keep the source stream.", False)]
        groups = (("Lossless", lambda c: c.lossless), ("Lossy", lambda c: not c.lossless and not c.hw),
                  ("Hardware", lambda c: c.hw))
        for group, match in groups:
            for c in CODECS:
                if not match(c):
                    continue
                st = self.encoders.get(c.key) if self.encoders else None
                if self.encoders is None:
                    items.append((f"{group}: {c.label}", c.key, "Detecting encoders…", False))
                elif st and st.available:
                    items.append((f"{group}: {c.label}", c.key, c.description, True))
                else:
                    reason = st.reason if st else "unknown"
                    items.append((f"{group}: {c.label}  (unavailable)", c.key,
                                  f"{c.description}\n\nNot available: {reason}", False))
        return items

    def _smart_summary(self, clip: Clip) -> list[str]:
        job = clip.job
        if clip.joins is None:
            return ["Analysing the keyframes of this clip …"]
        parts = job.smart_parts()
        encoded = [p for p in parts if p.kind == "encode"]
        lines = [f"Codec: {job.codec.label} – always the source codec, so the parts can be "
                 "joined."]
        if not encoded:
            lines.append("No section is marked “Re-encode” (Preview & trim tab) – the whole "
                         "clip is copied.")
        else:
            n_copy = sum(p.frames for p in parts if p.kind == "copy")
            n_enc = sum(p.frames for p in encoded)
            lines.append(f"{len(parts)} parts: {n_copy} frames copied, {n_enc} frames "
                         f"re-encoded in {len(encoded)} part(s).")
        lines.append(f"Parts can only be joined at keyframes (here every "
                     f"{_key_interval(job.frames)} frames): in / out points snap to them and "
                     "re-encoded sections are widened to the nearest ones – the extra frames "
                     "are re-encoded at the speed they have anyway.")
        lines.append(f"<span style='color:#d35400'>⚠ {smart.APPLE_WARNING}</span>")
        lines.append(f"{job.source_frame_count} → {job.output_frame_count} frames, "
                     f"{fmt_duration(job.output_duration)}")
        ext = formats.CONTAINER_EXT[job.container]
        lines.append(f"File: {job.default_output_name()}{ext}")
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
            src = f"Source ({chroma_label(info.chroma)})"
            fill_combo(self.chroma_combo, [(src, None)], None)
            fill_combo(self.depth_combo, [(f"Source ({info.bit_depth}-bit)", None)], None)
            for w in (self.chroma_combo, self.depth_combo):
                w.setEnabled(False)
                w.setToolTip("Lossless retime keeps the source format.")
            return
        allowed = formats.allowed_formats(codec, job.profile, self.supported_pix_fmts(clip))
        chromas = sorted({c for c, _ in allowed}, key=CHROMA_ORDER.get)
        depths = sorted({d for _, d in allowed})
        src_rank = CHROMA_ORDER.get(info.chroma, 3)
        chroma_items = [(f"Like source ({chroma_label(info.chroma)})", None,
                         "Keep the source subsampling if the codec supports it.")]
        for c in chromas:
            label, tip = formats.CHROMA[c]
            if CHROMA_ORDER[c] > src_rank:
                tip += "\n\n" + formats.CHROMA_UPSAMPLE_NOTE
            chroma_items.append((label, c, tip))
        depth_items = [(f"Like source ({info.bit_depth}-bit)", None,
                        "Keep the source bit depth (8 or 10-bit) if the codec supports it.")]
        depth_items += [(formats.DEPTHS[d][0], d, formats.DEPTHS[d][1]) for d in depths]
        fill_combo(self.chroma_combo, chroma_items, s.chroma)
        fill_combo(self.depth_combo, depth_items, s.depth)
        for w in (self.chroma_combo, self.depth_combo):
            w.setEnabled(True)
        self.chroma_combo.setToolTip(self.chroma_combo.currentData() and
                                     formats.CHROMA[self.chroma_combo.currentData()][1] or
                                     "Chroma subsampling – how much colour detail is stored.")
        self.depth_combo.setToolTip("Bit depth – number of brightness / colour steps.")

    def _summary(self, clip: Clip) -> str:
        job = clip.job
        lines = [f"<b>{MODE_LABELS[job.mode]}</b>"]
        if job.mode == Mode.SMART:
            return "<br>".join(lines + self._smart_summary(clip))
        if job.has_segments:
            n = sum(1 for g in job.segments if g.start < job.trim_end and g.end > job.trim.start)
            if job.mode == Mode.RETIME:
                lines.append(f"{n} speed section(s), rest in real time – every frame keeps its "
                             "own duration (variable frame rate). Plays in all common players; "
                             "editing programs prefer a constant frame rate (choose a codec).")
                fastest = max(p.rate for p in job.pieces())
                if fastest > clip.info.real_fps:
                    lines.append(
                        f"<span style='color:#d35400'>Fast sections keep every frame: a player "
                        f"has to decode {fmt_rate(fastest)} frames per second there, which most "
                        "computers can't – it will stutter. For smooth playback choose a codec: "
                        "the constant frame rate then skips the extra frames.</span>")
            else:
                lines.append(f"{n} speed section(s), rest in real time – re-encoded to a constant "
                             f"{fmt_rate(job.settings.fps)} fps.")
                if rife.MODELS and job.settings.interpolation in rife.MODELS:
                    lines.append("<span style='color:#c0392b'>RIFE cannot be combined with speed "
                                 "sections – choose another interpolation.</span>")
        if (job.codec and job.codec.external and job.mode == Mode.INTERPOLATE
                and job.settings.interpolation in rife.MODELS):
            lines.append("<span style='color:#c0392b'>RIFE cannot be combined with AV2 – "
                         "choose another interpolation.</span>")
        if job.codec and job.codec.external:
            lines.append("<span style='color:#d35400'>AV2 reference encoder: ~75 s per 1080p "
                         "frame – test encodes use at most 5 frames.</span>")
        if rife.is_rife(job) and (clip.info.bit_depth > 8 or clip.info.is_hdr):
            lines.append(f"<span style='color:#d35400'>{RIFE_8BIT}</span>")
        if job.mode == Mode.RETIME:
            blockers = job.retime_blockers()
            if blockers:
                lines.append("<span style='color:#c0392b'>Lossless retime is not possible:<br>• "
                             + "<br>• ".join(blockers)
                             + "<br>Choose “lossless speed”, keep the source size, "
                               "or pick a codec to re-encode.</span>")
            else:
                lines.append("Trimming is only possible at keyframes. "
                             f"<span title='{KEYFRAME_TRIM_REASON}'>(why?)</span>")
        rate = ("variable frame rate" if job.has_segments and job.mode == Mode.RETIME
                else f"{float(job.settings.fps):.5g} fps")
        lines.append(f"{job.source_frame_count} → {job.output_frame_count} frames, "
                     f"{fmt_duration(job.output_duration)} at {rate}")
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
            lines.append(f"{w}×{h}, {clip.info.pix_fmt} (unchanged)")
        ext = formats.CONTAINER_EXT[job.container]
        lines.append(f"File: {job.default_output_name()}{ext}")
        return "<br>".join(lines)


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


def _row(*widgets) -> QWidget:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return w
