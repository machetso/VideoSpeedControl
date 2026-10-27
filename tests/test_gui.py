# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""GUI tests – run headless with the Qt 'offscreen' platform."""
from __future__ import annotations

import os
import tempfile
import time
from fractions import Fraction

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # never real windows (desktop may set wayland)
from PySide6.QtCore import QSettings, QUrl  # noqa: E402
from PySide6.QtGui import QTextDocument  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

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


def _cell(window, row: int, column: str):
    model = window.model
    return model.data(model.index(row, model.COLUMNS.index(column)))


def _pick(combo, data):
    idx = combo.findData(data)
    assert idx >= 0, data
    combo.setCurrentIndex(idx)


def test_import_and_info(window):
    clips = window.model.clips
    assert [c.path.name for c in clips] == ["h264_240.mp4", "hevc10_240.mp4"]
    assert window.current_clip() is clips[0]
    assert _cell(window, 1, "Codec").startswith("hevc")
    assert _cell(window, 1, "Format") == "4:2:0 10-bit"
    assert "every ≈ 24 frames" in window.info.values["Keyframes"].text()
    assert "lossless" in _cell(window, 0, "Output")


def test_settings_change_mode(window):
    panel, clip = window.settings, window.current_clip()
    assert clip.job.mode == Mode.RETIME
    assert not panel.speed_custom.isEnabled()               # lossless: speed is locked
    panel.set_process("reencode")
    assert clip.settings.codec == "x264"                    # re-encode needs a real codec
    panel.speed_custom.setChecked(True)
    panel.speed_spin.setValue(0.05)
    assert clip.settings.speed == Fraction(1, 20)
    assert clip.job.mode == Mode.INTERPOLATE and panel.interp_combo.isEnabled()
    assert panel.preset_combo.isVisibleTo(panel) and panel.quality_combo.currentData() == "18"
    assert panel.quality_combo.currentText() == "High (CRF 18)"
    assert panel.preset_combo.currentText() == "medium – balanced (default)"
    assert "C – interpolation" == _cell(window, 0, "Output")

    _pick(panel.res_combo, "hd720")
    _pick(panel.aspect_combo, "1:1")
    _pick(panel.fit_combo, "crop")
    assert (clip.settings.resize, clip.settings.width, clip.settings.height) == ("exact", 1280, 1280)
    assert clip.job.output_size() == (1280, 1280)


def test_chroma_options_follow_codec(window):
    panel, clip = window.settings, window.current_clip()
    panel.set_process("reencode")
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
    panel.set_process("reencode")
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
    assert _cell(window, 0, "Frames") == "480 of 959"
    assert "480 → " in settings.summary.text()

    settings.set_process("reencode")                  # frame-exact from now on
    panel.set_in(30)
    assert first.trim.start == 30 and not panel.note.text()

    settings.set_process("lossless")                  # back to A: the trim snaps again
    assert (first.trim.start, first.trim.end) == (24, 504)
    assert not panel.snap_button.isVisibleTo(panel)

    settings.apply_button.click()                     # trims are per clip
    assert second.trim.start == 0 and second.trim.end is None
    panel.clear_trim()
    assert first.trim.end is None


def test_test_encode_and_estimates(qapp, window):
    settings, panel = window.settings, window.test_panel
    first, second = window.model.clips
    settings.set_process("reencode")
    _pick(settings.codec_combo, "x264")
    _pick(settings.preset_combo, "ultrafast")
    settings.speed_custom.setChecked(True)
    settings.speed_spin.setValue(0.05)
    window.preview.seek(200)
    panel.frames_spin.setValue(20)
    panel.run_button.click()
    assert first.testing and _cell(window, 0, "Estimate") == "testing…"
    _wait(qapp, lambda: not first.testing)
    test = first.test
    assert test.ok and test.frames == 21 and test.source_start == 200
    assert "frames/s" in panel.result.text() and "Estimate for the whole clip" in panel.result.text()
    est = _cell(window, 0, "Estimate")
    assert est and not est.startswith("≈")
    assert "without estimate" in window.batch_label.text()      # second clip: other settings

    # comparison: output frame 10 ↔ source frame 205 (21 output frames from 10 source frames)
    _pick(panel.mode_combo, "wipe")
    panel.slider.setValue(10)
    assert "source frame 205" in panel.frame_label.text()
    _wait(qapp, lambda: panel.view.source is not None and panel.view.output is not None)

    settings.apply_button.click()                                 # same settings → derived
    assert _cell(window, 1, "Estimate").startswith("≈")
    assert "without estimate" not in window.batch_label.text()

    _pick(settings.quality_combo, "28")                          # test is stale now
    assert "changed after this test" in panel.result.text()
    assert _cell(window, 0, "Estimate") == ""
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
    settings.set_process("reencode")
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
    # extract, rife, encode + adding the sound
    assert len(first.test.commands) == 4 and "rife-ncnn-vulkan" in first.test.commands[1][0]
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


def test_frame_rate_list_and_lossless_only(window):
    panel, clip = window.settings, window.current_clip()
    src = clip.info.fps
    idx = panel.fps_combo.findData(str(src))
    assert idx >= 0 and "(original)" in panel.fps_combo.itemText(idx)
    assert "real time" in panel.fps_combo.itemText(idx)
    half = panel.fps_combo.itemText(panel.fps_combo.findData("25"))
    assert "slower" in half or "faster" in half or "real time" in half

    panel.set_process("reencode")
    _pick(panel.codec_combo, "x264")
    _pick(panel.res_combo, "hd1080")
    panel.speed_custom.setChecked(True)
    panel.set_process("lossless")
    s = clip.settings
    assert s.codec == "copy" and s.speed is None and s.resize == "source"
    assert clip.job.mode == Mode.RETIME and not clip.job.retime_blockers()
    assert not panel.codec_combo.isEnabled() and panel.fps_combo.isEnabled()
    _pick(panel.fps_combo, "60")
    assert clip.settings.fps == 60 and clip.job.mode == Mode.RETIME
    panel.set_process("reencode")
    assert panel.codec_combo.isEnabled()


def test_play_preview(qapp, window):
    panel, clip = window.preview, window.current_clip()
    clip.trim = type(clip.trim)(0, 40)
    panel.seek(0)
    window.settings.set_process("lossless")
    shown = []
    panel.player.frame.connect(lambda img, frame, behind: shown.append(frame))
    panel.toggle_play()
    assert panel.player.playing and panel.play_button.text().startswith("■")
    _wait(qapp, lambda: panel.play_button.text().startswith("▶"))   # finished was delivered
    assert shown and shown == sorted(shown) and shown[-1] < clip.trim.end   # snapped out-point
    assert panel.play_button.text().startswith("▶")


def test_keyframe_hint_in_lossless_mode(window):
    panel, settings = window.preview, window.settings
    settings.set_process("lossless")
    assert not panel.key_hint.isHidden() and "keyframes" in panel.key_hint.text()
    k = window.current_clip().frames.keyframes
    panel.set_in(k[1] + 1)
    assert window.current_clip().trim.start in k      # snapped
    settings.set_process("reencode")
    _pick(settings.codec_combo, "x264")
    assert panel.key_hint.isHidden()


def test_speed_sections_ui(qapp, window):
    panel, settings, clip = window.preview, window.settings, window.current_clip()
    settings.set_process("lossless")
    panel.seek(13)
    panel.section_start()
    panel.seek(32)
    panel.section_end()
    assert panel.sec_add.isEnabled()
    _pick(panel.sec_fps, "25")
    panel.add_section()
    assert [(s.start, s.end, s.fps) for s in clip.segments] == [(13, 33, 25)]   # not snapped
    assert not panel.sections_table.isHidden() and panel.sections_table.rowCount() == 1
    job = clip.job
    assert job.has_segments and job.mode == Mode.RETIME
    assert not settings.fps_combo.isEnabled()            # VFR: no output frame rate
    assert "Sections" in window.model.data(window.model.index(0, window.model.COLUMNS.index("Output")))

    settings.set_process("reencode")
    _pick(settings.codec_combo, "x264")
    _pick(settings.fps_combo, "60")
    assert settings.fps_combo.isEnabled() and clip.job.output_frame_count == round(
        clip.job.output_duration * 60)

    panel._set_section_fps(0, "50")
    assert clip.segments[0].fps == 50
    panel.remove_section(0)
    assert not clip.segments and panel.sections_table.isHidden()


def test_section_speedup_choices(window):
    panel, clip = window.preview, window.current_clip()
    real = clip.info.real_fps
    datas = [panel.sec_fps.itemData(i) for i in range(panel.sec_fps.count())]
    assert str(real * 8) in datas and str(real * 2) in datas
    texts = [panel.sec_fps.itemText(i) for i in range(panel.sec_fps.count())]
    assert any("8× faster" in t for t in texts)
    assert all(Fraction(d) <= real * 8 for d in datas)


def test_processing_modes_and_smart(qapp, window):
    settings, preview, clip = window.settings, window.preview, window.current_clip()
    _wait(qapp, lambda: clip.joins is not None)              # keyframe analysis in background
    assert settings.proc_lossless.isChecked() and settings.proc_smart.isEnabled()

    settings.set_process("smart")
    s = clip.settings
    assert s.smart and s.codec == "x264" and clip.job.mode == Mode.SMART
    assert not settings.codec_combo.isEnabled() and not settings.res_combo.isEnabled()
    assert not settings.fps_combo.isEnabled() and not settings.speed_custom.isEnabled()
    assert settings.quality_combo.isEnabled() and settings.preset_combo.isEnabled()
    containers = [settings.container_combo.itemData(i) for i in range(settings.container_combo.count())]
    assert containers == ["mp4", "mkv"]
    assert "Apple" in settings.summary.text() and "keyframes" in settings.summary.text()
    assert "Smart re-encode joins" in preview.key_hint.text()

    preview.seek(30)
    preview.section_start()
    preview.seek(40)
    preview.section_end()
    _pick(preview.sec_fps, "25")
    preview.add_section()
    t = preview.sections_table
    assert not t.isColumnHidden(4) and not t.isColumnHidden(5)
    preview._set_section(0, reencode=True, out_fps=Fraction(25))
    parts = clip.job.smart_parts()
    assert [p.kind for p in parts] == ["copy", "encode", "copy"]
    assert "re-encoded in 1 part" in settings.summary.text()

    settings.set_process("reencode")
    assert not clip.settings.smart and t.isColumnHidden(4) and settings.codec_combo.isEnabled()
    settings.set_process("lossless")
    assert clip.settings.codec == "copy" and not settings.quality_combo.isEnabled()


def test_magnetic_cursor(window):
    panel, clip = window.preview, window.current_clip()
    tl = panel.timeline
    tl.resize(1000, tl.height())
    panel.seek(100)
    panel.section_start()
    panel.seek(199)
    panel.section_end()
    panel.add_section()                                  # section 100–199
    near_end = tl.x_of(200.5) + 4                        # a few px right of the border
    assert tl._snap(near_end) == 200 and tl.magnet_hit == 200    # first frame after it
    tl._drag = "seek"
    tl._drag_to(near_end)                                # dragging there moves the cursor
    tl._drag = None
    assert clip.playhead == 200
    panel.section_start()
    assert tl.pending == (200, None)
    near_start = tl.x_of(99.5) - 4
    assert tl._snap(near_start) == 99 and tl.magnet_hit == 100   # marking an end: frame before
    panel.magnet_button.setChecked(False)
    assert tl._snap(near_end) != 200 or tl.frame_at(near_end) == 200
    assert tl.magnet_hit is None
    panel.magnet_button.setChecked(True)


def test_quick_preview_picture(qapp, window):
    panel, clip = window.preview, window.current_clip()
    _wait(qapp, lambda: clip.proxy_done, timeout=60)
    assert all(p is not None for p in clip.proxy) and len(clip.proxy) == clip.frames.count
    panel.seek(500)
    quick = panel.view.image
    assert quick is not None and quick.width() <= 384                          # instant, small
    _wait(qapp, lambda: panel.fetcher.shown and panel.fetcher.shown[1] == 500)
    assert panel.view.image is not quick                                       # then the exact
    assert (panel.view.image.width(), panel.view.image.height()) == panel._exact_size


def test_batch_list_and_clear_sections(qapp, window, tmp_path, monkeypatch):
    from vsc.gui.batch_dialogs import AdditionDialog
    monkeypatch.setattr(AdditionDialog, "exec", lambda d: True)     # "another encoding": yes
    monkeypatch.setattr(AdditionDialog, "keys", lambda d: ())       # no name additions
    preview, settings, export = window.preview, window.settings, window.export_panel
    clip = window.current_clip()
    _wait(qapp, lambda: clip.joins is not None)
    for a, b, fps in ((24, 71, "25"), (72, 119, "60")):          # two seamless sections
        preview.seek(a); preview.section_start()
        preview.seek(b); preview.section_end()
        _pick(preview.sec_fps, fps); preview.add_section()
    clip.trim = type(clip.trim)(0, 192)
    settings.set_process("lossless")
    preview.batch_button.click()
    assert export.batch_list() and len(window.batch_entries) == 1
    assert len(clip.segments) == 2                                # not removed by adding
    settings.set_process("smart")
    preview._set_section(0, reencode=True, out_fps=Fraction(25))
    preview.batch_button.click()
    labels = [export.queue.topLevelItem(i).text(0) for i in range(export.queue.topLevelItemCount())]
    assert len(labels) == 2 and "Lossless, 2 sections" in labels[0] and "Smart" in labels[1]
    assert window.batch_entries[0].job.settings.codec == "copy"   # snapshot, not live

    preview.clear_sections()
    assert not clip.segments and preview.undo_button.isEnabled()
    preview.undo()
    assert len(clip.segments) == 2 and preview.redo_button.isEnabled()

    export.to_folder.setChecked(True)
    export.folder.setText(str(tmp_path))
    export.pattern.setText("{name}_{mode}")
    _pick(export.policy, "rename")
    names = [export.queue.topLevelItem(i).text(1) for i in range(2)]
    assert names == ["h264_240_lossless.mp4", "h264_240_smart.mp4"]
    export.start_button.click()
    _wait(qapp, lambda: window._batch is None, timeout=120)
    assert (tmp_path / "h264_240_lossless.mp4").stat().st_size > 1000
    assert (tmp_path / "h264_240_smart.mp4").stat().st_size > 1000
    assert len(window.batch_entries) == 2                         # list kept after export
    assert all(e.done for e in window.batch_entries)

    # entries added later: only they run, the exported ones are kept but not run again
    settings.set_process("lossless")
    preview.batch_button.click()
    window._plan_export()
    status = [export.queue.topLevelItem(i).text(2) for i in range(3)]
    assert status[0].startswith("Done") and status[1].startswith("Done") and status[2] == "renamed (_2)"
    assert "1 clip(s) will be exported" in export.message.text()
    before = {f: f.stat().st_mtime_ns for f in tmp_path.iterdir()}
    export.start_button.click()
    _wait(qapp, lambda: window._batch is None, timeout=120)
    after = {f: f.stat().st_mtime_ns for f in tmp_path.iterdir()}
    assert all(after[f] == t for f, t in before.items())          # earlier files untouched
    assert len(after) == 3 and window.batch_entries[2].done
    assert "1 done" in export.message.text()
    window.batch_entries[1].exported.unlink()                     # file gone → export again
    window._plan_export()
    assert "1 clip(s) will be exported" in export.message.text()
    window._remove_entries([2])

    export.queue.topLevelItem(0).setSelected(True)
    export.remove_button.click()
    assert len(window.batch_entries) == 1
    export.clear_button.click()
    assert not window.batch_entries


def test_clear_sections_asks_first(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    preview, clip = window.preview, window.current_clip()
    preview.seek(10); preview.section_start(); preview.seek(20); preview.section_end()
    preview.add_section()
    answers = iter([QMessageBox.Cancel, QMessageBox.Yes])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: next(answers))
    preview.clear_sections_button.click()
    assert len(clip.segments) == 1                       # cancelled
    preview.clear_sections_button.click()
    assert not clip.segments and preview.undo_button.isEnabled()


def test_section_table_keeps_position_and_out_fps(qapp, window):
    from PySide6.QtCore import QSettings
    QSettings().remove("sections/out_fps")
    preview, settings = window.preview, window.settings
    clip = window.current_clip()
    _wait(qapp, lambda: clip.joins is not None)
    settings.set_process("smart")
    for i in range(8):                                   # more rows than the table shows
        preview.seek(10 + i * 40); preview.section_start()
        preview.seek(30 + i * 40); preview.section_end()
        preview.add_section()
    t = preview.sections_table

    def fully_visible(row):
        qapp.processEvents()
        rect = t.visualRect(t.model().index(row, 0))
        return t.viewport().rect().contains(rect)
    assert t.verticalScrollBar().maximum() > 0
    assert fully_visible(7) and not fully_visible(0)            # newest (last) row in view
    preview._set_section(7, reencode=True)
    assert fully_visible(7)                                      # stays down
    assert clip.segments[7].out_fps == 30                         # built-in default
    preview._set_section(7, out_fps=Fraction(25))
    preview.seek(400); preview.section_start(); preview.seek(420); preview.section_end()
    preview.add_section()
    assert clip.segments[-1].out_fps == 25                        # last choice is the default
    QSettings().remove("sections/out_fps")


def test_quality_levels_and_custom(window):
    panel, clip = window.settings, window.current_clip()
    panel.set_process("reencode")
    names = [panel.quality_combo.itemText(i) for i in range(panel.quality_combo.count())]
    assert names[0].startswith("Visually lossless") and names[-1] == "Custom…"
    assert not panel.quality_spin.isVisibleTo(panel)
    _pick(panel.quality_combo, "23")
    assert clip.settings.quality == 23
    _pick(panel.quality_combo, "custom")
    assert panel.quality_spin.isVisibleTo(panel)
    panel.quality_spin.setValue(21)
    assert clip.settings.quality == 21 and panel.quality_combo.currentData() == "custom"
    _pick(panel.codec_combo, "svtav1")                          # other scale, own levels
    assert clip.settings.quality is None and panel.quality_combo.currentText() == "High (CRF 30)"


def test_help_about_and_icons(qapp, window):
    from vsc.gui import help
    icon = help.app_icon()
    assert {s.width() for s in icon.availableSizes()} >= {16, 32, 48, 256}
    assert not help.splash_pixmap(400).isNull() and help.ICON_SIZES
    assert help.MANUAL.is_file() and help.PDF.is_file()
    window.show_help()
    h = window._help
    titles = [t for _, t in h.headings]
    assert "7. Smart re-encode" in titles and "13. Licence and credits" in titles
    h.toc.setCurrentRow(titles.index("9. Export and the batch list"))
    assert h.browser.textCursor().block().text() == "9. Export and the batch list"
    doc = h.browser.document()
    for name in ("overview", "sections", "export"):                 # pictures are loaded
        assert doc.resource(QTextDocument.ImageResource, QUrl(f"images/{name}.png")) is not None
    about = help.AboutDialog(window)
    assert any("MIT License" in label.text() for label in about.findChildren(QLabel))
    h.close()


def test_sound_button(window):
    panel = window.settings
    first, second = window.model.clips                     # h264 with sound, hevc10 without
    b = panel.audio_button
    assert b.isEnabled() and b.isChecked() and b.text().startswith("🔊")
    b.click()
    assert first.settings.audio is False and b.text().startswith("🔇")
    assert "Sound: none" in panel.summary.text()
    b.click()
    assert first.settings.audio is True and "pitch preserved" in panel.summary.text()
    window._select(second)
    assert not b.isEnabled() and "no sound" in b.toolTip()


def _add_sections(preview, ranges):
    for a, b, fps in ranges:
        preview.seek(a); preview.section_start()
        preview.seek(b); preview.section_end()
        _pick(preview.sec_fps, fps); preview.add_section()


def test_section_undo_redo_many_steps(window):
    preview, clip = window.preview, window.current_clip()
    assert not preview.undo_button.isEnabled() and not preview.redo_button.isEnabled()
    _add_sections(preview, ((10, 20, "25"), (30, 40, "25"), (50, 60, "60")))
    preview._set_section(0, fps=Fraction(60))
    preview.remove_section(1)
    preview.clear_sections()
    assert not clip.segments and len(clip.undo_steps) == 6
    assert "clear 2 sections" in preview.undo_button.toolTip()
    states = []
    while clip.undo_steps:
        preview.undo()
        states.append([(s.start, s.fps) for s in clip.segments])
    assert states == [[(10, 60), (50, 60)],
                      [(10, 60), (30, 25), (50, 60)],
                      [(10, 25), (30, 25), (50, 60)],
                      [(10, 25), (30, 25)], [(10, 25)], []]
    assert not preview.undo_button.isEnabled()
    for _ in range(3):
        preview.redo()
    assert [s.start for s in clip.segments] == [10, 30, 50]
    _add_sections(preview, ((70, 80, "25"),))               # a new edit drops the redo steps
    assert not clip.redo_steps and not preview.redo_button.isEnabled()
    other = window.model.clips[1]                           # history is per clip
    window._select(other)
    assert not preview.undo_button.isEnabled()
    window._select(clip)
    assert preview.undo_button.isEnabled()


def test_treatment_save_and_load(qapp, window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    preview, settings = window.preview, window.settings
    clip = window.current_clip()
    _add_sections(preview, ((24, 71, "25"), (72, 119, "60")))
    settings.set_process("reencode")
    clip.settings.preset = "slow"
    clip.trim = type(clip.trim)(0, 192)
    cst = tmp_path / "h264.cst"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(cst), ""))
    window.save_treatment()
    assert cst.is_file()

    saved = [(s.start, s.end, s.fps) for s in clip.segments]
    preview.clear_sections()
    settings.set_process("lossless")
    clip.trim = type(clip.trim)()
    window.add_files([cst])                         # dropping / opening a .cst loads it
    assert [(s.start, s.end, s.fps) for s in clip.segments] == saved
    assert clip.settings.codec == "x264" and clip.settings.preset == "slow"
    assert clip.trim.end == 192 and window.current_clip() is clip

    other = window.model.clips[1]                   # wrong clip selected: still finds its clip
    window._select(other)
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.Yes)
    window.open_treatment(cst)                      # clip has sections → asks before replacing
    assert asked and window.current_clip() is clip and not other.segments
    assert "load h264.cst" in clip.undo_steps[-1][0]

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    window._apply_treatment(other, cst, __import__("vsc.core.treatment").core.treatment.load(cst))
    assert warnings and "another video" in warnings[0] and not other.segments


def test_batch_entry_edit_and_another_encoding(qapp, window, tmp_path, monkeypatch):
    from vsc.gui import batch_dialogs
    from vsc.gui.batch_dialogs import AdditionDialog
    preview, settings, export = window.preview, window.settings, window.export_panel
    clip = window.current_clip()
    export.to_folder.setChecked(True)
    export.folder.setText(str(tmp_path))
    export.pattern.setText("{name}")
    _add_sections(preview, ((24, 71, "25"),))
    settings.set_process("reencode")
    preview.batch_button.click()
    assert len(window.batch_entries) == 1           # first one: no question

    preview.clear_sections()
    settings.set_process("lossless")
    monkeypatch.setattr(batch_dialogs, "ask_entry_action", lambda *a: batch_dialogs.EDIT)
    monkeypatch.setattr("vsc.gui.main_window.ask_entry_action", lambda *a: batch_dialogs.EDIT)
    window._open_entry(0)                           # the entry comes back into the editor
    assert [s.start for s in clip.segments] == [24] and clip.settings.codec == "x264"
    assert preview.update_button.isVisibleTo(preview)
    clip.settings.preset = "veryslow"
    preview.update_button.click()
    assert window.batch_entries[0].job.settings.preset == "veryslow"
    assert len(window.batch_entries) == 1 and not preview.update_button.isVisibleTo(preview)

    monkeypatch.setattr("vsc.gui.main_window.ask_entry_action", lambda *a: batch_dialogs.NEW)
    window._open_entry(0)
    assert not preview.update_button.isVisibleTo(preview)
    clip.settings.codec = "x265"
    seen = {}

    def fake_exec(dialog):
        seen["boxes"] = {k: b.text() for k, b in dialog.boxes.items()}
        for key, box in dialog.boxes.items():
            box.setChecked(key in ("codec", "res"))
        seen["preview"] = dialog.preview.text()
        dialog.accept()
        return True
    monkeypatch.setattr(AdditionDialog, "exec", fake_exec)
    preview.batch_button.click()
    assert len(window.batch_entries) == 2
    assert seen["boxes"]["codec"] == "Codec: x265" and seen["boxes"]["preset"] == "Preset: veryslow"
    assert "h264_240_x265_1280x720.mp4" in seen["preview"]
    names = [export.queue.topLevelItem(i).text(1) for i in range(2)]
    assert names == ["h264_240.mp4", "h264_240_x265_1280x720.mp4"]

    monkeypatch.setattr(AdditionDialog, "exec", lambda dialog: False)   # cancelled
    preview.batch_button.click()
    assert len(window.batch_entries) == 2
