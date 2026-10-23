"""GUI tests – run headless with the Qt 'offscreen' platform."""
from __future__ import annotations

import os
import time
from fractions import Fraction

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from vsc.core.job import Mode  # noqa: E402
from vsc.gui.clips import Status  # noqa: E402
from vsc.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _wait(qapp, condition, timeout=30.0):
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "timed out"
        qapp.processEvents()
        time.sleep(0.01)


@pytest.fixture
def window(qapp, h264_clip, hevc10_clip):
    w = MainWindow()
    w.add_files([h264_clip, hevc10_clip, h264_clip])   # duplicate is ignored
    _wait(qapp, lambda: w.settings.encoders is not None and
          all(c.status == Status.READY for c in w.model.clips))
    yield w
    w.close()


def _pick(combo, data):
    idx = combo.findData(data)
    assert idx >= 0, data
    combo.setCurrentIndex(idx)


def test_import_and_info(window):
    clips = window.model.clips
    assert [c.path.name for c in clips] == ["h264_240.mp4", "hevc10_240.mp4"]
    assert window.current_clip() is clips[0]
    assert window.model.data(window.model.index(1, 1)).startswith("hevc")
    assert window.model.data(window.model.index(1, 6)) == "4:2:0 10-bit"
    assert "every ≈ 24 frames" in window.info.values["Keyframes"].text()
    assert "lossless" in window.model.data(window.model.index(0, 7))


def test_settings_change_mode(window):
    panel, clip = window.settings, window.current_clip()
    assert clip.job.mode == Mode.RETIME
    panel.speed_custom.setChecked(True)
    panel.speed_spin.setValue(0.05)
    assert clip.settings.speed == Fraction(1, 20)
    assert "not possible" in panel.summary.text()          # copy + wrong speed

    _pick(panel.codec_combo, "x264")
    assert clip.job.mode == Mode.INTERPOLATE and panel.interp_combo.isEnabled()
    assert panel.preset_combo.isVisibleTo(panel) and panel.quality_spin.value() == 18
    assert "C – interpolation" == window.model.data(window.model.index(0, 7))

    _pick(panel.res_combo, "hd720")
    _pick(panel.aspect_combo, "1:1")
    _pick(panel.fit_combo, "crop")
    assert (clip.settings.resize, clip.settings.width, clip.settings.height) == ("exact", 1280, 1280)
    assert clip.job.output_size() == (1280, 1280)


def test_chroma_options_follow_codec(window):
    panel, clip = window.settings, window.current_clip()
    _pick(panel.codec_combo, "prores")
    chroma = [panel.chroma_combo.itemData(i) for i in range(panel.chroma_combo.count())]
    assert chroma == [None, "422"]                           # ProRes HQ: 4:2:2 only
    _pick(panel.profile_combo, "4444")
    chroma = [panel.chroma_combo.itemData(i) for i in range(panel.chroma_combo.count())]
    assert chroma == [None, "444"]
    assert clip.job.output_format(panel._supported(clip))[:2] == ("444", 10)


def test_apply_to_all_and_per_clip(window):
    panel = window.settings
    first, second = window.model.clips
    _pick(panel.fps_combo, "50")
    _pick(panel.res_combo, "hd1080")
    assert second.settings.fps != Fraction(50)              # settings are per clip
    panel.apply_button.click()
    assert second.settings.fps == Fraction(50) and second.ui["res"] == "hd1080"
    second.settings.fps = Fraction(25)
    assert first.settings.fps == Fraction(50)               # copies, not shared

    window._select(second)
    assert panel.clip is second and panel.fps_combo.currentData() == "25"
