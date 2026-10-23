"""Output settings of the selected clip, plus a live summary of what will happen.

Every edit is written straight into the clip's OutputSettings; afterwards all widgets are
re-synchronised from the settings, so dependent choices (containers, profiles, chroma …)
always match the chosen codec.
"""
from __future__ import annotations

from fractions import Fraction

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..core import formats
from ..core.encoders import EncoderStatus
from ..core.formats import COPY, CODECS
from ..core.job import KEYFRAME_TRIM_REASON, MODE_LABELS, Mode, _even
from .clips import Clip, chroma_label, fmt_duration

CUSTOM = "custom"
SPEED_PRESETS = [Fraction(1, n) for n in (2, 4, 5, 8, 10, 16, 20, 32)]
CHROMA_ORDER = {"411": 0, "420": 1, "422": 2, "444": 3}
NOT_YET = "Planned for a later version (RIFE integration, milestone 5)."


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
        self._loading = False

        form_widget = QWidget()
        form = self.form = QFormLayout(form_widget)

        # --- frame rate
        self.fps_combo = QComboBox()
        self.fps_combo.setToolTip("Frame rate of the output file.")
        for label, fps in formats.FRAME_RATES:
            self.fps_combo.addItem(label, str(fps))   # Qt would turn a Fraction into a float
        self.fps_combo.addItem("Custom…", CUSTOM)
        self.fps_edit = QLineEdit()
        self.fps_edit.setPlaceholderText("e.g. 48 or 24000/1001")
        self.fps_edit.setMaximumWidth(140)
        form.addRow("Frame rate:", _row(self.fps_combo, self.fps_edit))

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

    def set_encoders(self, status: dict[str, EncoderStatus]) -> None:
        self.encoders = status
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

        codec = self.codec_combo.currentData()
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

        self._sync()
        self.changed.emit()

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

        # frame rate
        custom_fps = ui.get("fps") == CUSTOM or s.fps not in [f for _, f in formats.FRAME_RATES]
        self.fps_combo.setCurrentIndex(self.fps_combo.findData(CUSTOM if custom_fps else str(s.fps)))
        self.fps_edit.setVisible(custom_fps)
        if custom_fps and parse_fps(self.fps_edit.text()) != s.fps:
            self.fps_edit.setText(f"{s.fps.numerator}/{s.fps.denominator}"
                                  if s.fps.denominator != 1 else str(s.fps.numerator))

        # speed
        lossless = float(job.lossless_speed)
        self.speed_lossless.setText(f"Lossless speed: {lossless:.5g}×  "
                                    f"({1 / lossless:.3g}× slower)")
        self.speed_lossless.setChecked(s.speed is None)
        self.speed_custom.setChecked(s.speed is not None)
        self.speed_spin.setEnabled(s.speed is not None)
        self.speed_spin.setValue(float(job.speed))
        sp = float(job.speed)
        self.speed_info.setText(f"{sp:.5g}× = {sp * 100:.4g} % of real time → "
                                f"{1 / sp:.3g}× slower, output {fmt_duration(job.output_duration)}")

        # codec
        fill_combo(self.codec_combo, self._codec_items(), s.codec)
        codec = job.codec
        self.codec_combo.setToolTip(codec.description if codec else
                                    "Keeps the original video stream untouched; only the\n"
                                    "timestamps are changed. Fastest, no quality loss.")
        if codec is None:
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
        items = [(f"{i.label}  (quality {i.quality}/5)", i.key,
                  i.tooltip + ("\n\n" + NOT_YET if i.needs_gpu else ""), not i.needs_gpu)
                 for i in formats.INTERPOLATIONS]
        fill_combo(self.interp_combo, items, s.interpolation)
        interpolating = job.mode == Mode.INTERPOLATE
        self.interp_combo.setEnabled(interpolating)
        current = next(i for i in formats.INTERPOLATIONS if i.key == s.interpolation)
        self.interp_combo.setToolTip(current.tooltip if interpolating else
                                     "Only used when the speed is slower than the lossless speed.")

        self.summary.setText(self._summary(clip))

    def _codec_items(self) -> list[tuple]:
        items = [("Keep source codec – lossless retime", COPY,
                  "Keeps the original video stream untouched; only the timestamps\n"
                  "are changed. Fastest, no quality loss.", True)]
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

    def _supported(self, clip: Clip) -> list[str] | None:
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
        allowed = formats.allowed_formats(codec, job.profile, self._supported(clip))
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
        lines.append(f"{job.source_frame_count} → {job.output_frame_count} frames, "
                     f"{fmt_duration(job.output_duration)} at {float(job.settings.fps):.5g} fps")
        if job.codec:
            w, h = job.output_size()
            try:
                chroma, depth, pix = job.output_format(self._supported(clip))
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
