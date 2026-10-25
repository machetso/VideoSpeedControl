"""GUI tests – run headless with the Qt 'offscreen' platform."""
from __future__ import annotations

import os
import tempfile
import time
from fractions import Fraction

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from vsc.core.job import Mode  # noqa: E402
from vsc.gui.clips import Status  # noqa: E402
from vsc.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    # keep the export options of the tests out of the user's settings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp())
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
    assert clip.job.output_format(panel.supported_pix_fmts(clip))[:2] == ("444", 10)


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


def test_preview_frame_and_thumbnails(qapp, window):
    panel, clip = window.preview, window.current_clip()
    panel.seek(30)
    _wait(qapp, lambda: panel.fetcher.shown and panel.fetcher.shown[1] == 30)
    assert not panel.view.image.isNull()
    assert "Frame 30 of 958" in panel.position.text()
    _wait(qapp, lambda: all(clip.thumbs))
    assert all(t[0] in clip.frames.keyframes for t in clip.thumbs)
    panel.step_key(1)
    assert clip.playhead == 48
    panel.step_key(-1)
    assert clip.playhead == 24


def test_trim_snapping_and_modes(window):
    panel, settings = window.preview, window.settings
    first, second = window.model.clips
    panel.seek(30)
    panel.set_in(first.playhead)                      # mode A → keyframe 24
    assert first.trim.start == 24 and "moved to frame 24" in panel.note.text()
    panel.set_out(500)                                # last frame 500 → GOP ends at 504
    assert first.trim.end == 504
    assert window.model.data(window.model.index(0, 4)) == "480 of 959"
    assert "480 → " in settings.summary.text()

    _pick(settings.codec_combo, "x264")               # frame-exact from now on
    panel.set_in(30)
    assert first.trim.start == 30 and not panel.note.text()

    _pick(settings.codec_combo, "copy")               # back to A: trim is off the keyframes
    assert "not on keyframes" in settings.summary.text()
    assert panel.snap_button.isVisibleTo(panel)
    panel.snap_button.click()
    assert (first.trim.start, first.trim.end) == (24, 504)
    assert not panel.snap_button.isVisibleTo(panel)

    settings.apply_button.click()                     # trims are per clip
    assert second.trim.start == 0 and second.trim.end is None
    panel.clear_trim()
    assert first.trim.end is None


def test_test_encode_and_estimates(qapp, window):
    settings, panel = window.settings, window.test_panel
    first, second = window.model.clips
    _pick(settings.codec_combo, "x264")
    _pick(settings.preset_combo, "ultrafast")
    settings.speed_custom.setChecked(True)
    settings.speed_spin.setValue(0.05)
    window.preview.seek(200)
    panel.frames_spin.setValue(20)
    panel.run_button.click()
    assert first.testing and window.model.data(window.model.index(0, 8)) == "testing…"
    _wait(qapp, lambda: not first.testing)
    test = first.test
    assert test.ok and test.frames == 21 and test.source_start == 200
    assert "frames/s" in panel.result.text() and "Estimate for the whole clip" in panel.result.text()
    est = window.model.data(window.model.index(0, 8))
    assert est and not est.startswith("≈")
    assert "without estimate" in window.batch_label.text()      # second clip: other settings

    # comparison: output frame 10 ↔ source frame 205 (21 output frames from 10 source frames)
    _pick(panel.mode_combo, "wipe")
    panel.slider.setValue(10)
    assert "source frame 205" in panel.frame_label.text()
    _wait(qapp, lambda: panel.view.source is not None and panel.view.output is not None)

    settings.apply_button.click()                                 # same settings → derived
    assert window.model.data(window.model.index(1, 8)).startswith("≈")
    assert "without estimate" not in window.batch_label.text()

    settings.quality_spin.setValue(30)                            # test is stale now
    assert "changed after this test" in panel.result.text()
    assert window.model.data(window.model.index(0, 8)) == ""
    workdir = test.workdir
    window.clear()
    assert not workdir.exists()                                  # temp files removed


def test_zoom_state():
    from PySide6.QtCore import QPointF, QRectF
    from vsc.gui.zoom import ZoomState
    z = ZoomState()
    box = QRectF(0, 0, 400, 300)
    assert z.rect(1600, 900, box, 1.0) == QRectF(0, 37.5, 400, 225)          # fit
    z.set_zoom(1.0)
    assert z.rect(1600, 900, box, 1.0) == QRectF(-600, -300, 1600, 900)      # centred 1:1
    assert z.rect(1600, 900, box, 2.0).width() == 800                        # HiDPI: device px
    z.pan(QPointF(10000, 0), 1600, 900, 1.0)                                 # clamped at the edge
    assert z.rect(1600, 900, box, 1.0).x() == 0
    assert z.rect(200, 100, box, 1.0) == QRectF(100, 100, 200, 100)          # small: centred
    z.toggle_at(QPointF(0, 0), box)
    assert z.zoom is None


def test_zoom_requests_full_frames(qapp, window):
    preview_panel = window.preview
    preview_panel.seek(10)
    preview_panel.zoom.set_zoom(1.0)
    _wait(qapp, lambda: preview_panel.view.image is not None
          and preview_panel.view.image.width() == 1280)                      # native 1280×720
    dpr = preview_panel.view.devicePixelRatioF()
    assert preview_panel.view.drawn_rect().width() == 1280 / dpr


def test_rife_in_gui(qapp, window):
    from vsc.core import rife
    if not rife.detect().available:
        pytest.skip("RIFE / Vulkan not available")
    settings, panel = window.settings, window.test_panel
    first = window.model.clips[0]
    _pick(settings.codec_combo, "x264")
    _pick(settings.preset_combo, "ultrafast")
    _pick(settings.res_combo, "sd480")
    settings.speed_custom.setChecked(True)
    settings.speed_spin.setValue(0.05)
    idx = settings.interp_combo.findData("rife")
    assert settings.interp_combo.model().item(idx).isEnabled()
    assert "Runs on:" in settings.interp_combo.itemData(idx, 3)
    _pick(settings.interp_combo, "rife")
    assert first.settings.interpolation == "rife"
    panel.frames_spin.setValue(10)
    panel.run_button.click()
    _wait(qapp, lambda: not first.testing, timeout=120)
    assert first.test.ok, first.test.error
    assert first.test.frames >= 10
    assert len(first.test.commands) == 3 and "rife-ncnn-vulkan" in first.test.commands[1][0]
    assert "Estimate for the whole clip" in panel.result.text()


def test_export_queue(qapp, window, tmp_path):
    panel = window.export_panel
    (tmp_path / "01_h264_240.mp4").write_bytes(b"old")
    panel.to_folder.setChecked(True)
    panel.folder.setText(str(tmp_path))
    panel.pattern.setText("{n}_{name}")
    _pick(panel.policy, "rename")
    assert panel.queue.topLevelItemCount() == 2
    assert panel.queue.topLevelItem(0).text(1) == "01_h264_240_2.mp4"
    assert "renamed" in panel.queue.topLevelItem(0).text(2)

    _pick(panel.policy, "skip")
    assert panel.queue.topLevelItem(0).text(1) == "–"
    _pick(panel.scope, "selected")              # only the current (first) clip is selected
    assert panel.queue.topLevelItemCount() == 1 and not panel.start_button.isEnabled()

    _pick(panel.scope, "all")
    panel.start_button.click()
    assert window._batch is not None and not panel.start_button.isEnabled()
    assert not window._list_actions[0].isEnabled()           # no removing while exporting
    _wait(qapp, lambda: window._batch is None, timeout=120)
    clips = window.model.clips
    assert [c.export for c in clips] == ["Skipped (file exists)", "Exported"]
    assert panel.queue.topLevelItem(1).text(2).startswith("Done")
    assert (tmp_path / "01_h264_240.mp4").read_bytes() == b"old"
    assert (tmp_path / "02_hevc10_240.mp4").stat().st_size > 1000
    assert "1 done, 1 skipped" in panel.message.text()
    assert panel.start_button.isEnabled() and window._list_actions[0].isEnabled()
