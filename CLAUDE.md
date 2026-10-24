# VideoSpeedControl – developer notes

Read SCOPE.md for the agreed feature set and milestone status.

## Resume here
- Status 2026-10-25: milestone 4 committed (fdc0558). Milestone 5 (RIFE) + 1:1 zoom in preview
  and comparison implemented and committed, 56 tests green – user has not tried it yet.
- Next: milestone 6 – batch queue (output folder, name pattern, overwrite policy, per-clip and
  overall progress, cancel). `runner.create()` picks Runner / RifeRunner.
- Open option: enable Intel Quick Sync on the dev laptop (needs Intel media runtime / oneVPL).

## Setup
- Git: local repo, branch main. `.venv/`, `vendor/`, `tests/media/` are not committed –
  recreate with the setup steps below (tests regenerate their media).
- venv: `.venv/` (created with `--without-pip` + get-pip.py, because python3-venv/ensurepip is
  not installed system-wide). Run things with `.venv/bin/python`.
- FFmpeg: `python tools/fetch_ffmpeg.py [linux|windows]` → `vendor/ffmpeg/<platform>-x64/`.
  `vsc/core/ffmpeg_bin.py` prefers the bundled copy, then `VSC_FFMPEG_DIR`, then PATH.
- RIFE: `python tools/fetch_rife.py [linux|windows]` → `vendor/rife/<platform>-x64/`
  (rife-ncnn-vulkan 20221029 + rife-v4.6 model only; `VSC_RIFE_DIR` overrides). Tests that need
  it are skipped when RIFE / Vulkan is unavailable.
- Tests: `.venv/bin/python -m pytest tests -q` (test clips are generated into tests/media;
  shared fixtures in tests/conftest.py).
- CLI: `.venv/bin/python -m vsc info CLIP`, `... encode CLIP -o DIR --fps 25 [--codec x264 ...]`.

## Layout
- `vsc/core/` – no Qt imports; GUI-independent and testable.
  - `probe.py` – MediaInfo (ffprobe) and FrameMap (packet scan: exact pts, keyframes)
  - `formats.py` – catalogue: fps, resolutions, chroma, scalers, interpolation, codecs + UI texts
  - `encoders.py` – encoder detection, pix_fmt lists, hardware test encodes (cached in
    ~/.config/VideoSpeedControl/encoders.json per FFmpeg version)
  - `job.py` – OutputSettings (per clip), Trim, Job (mode decision, sizes, formats)
  - `command.py` – Job → ffmpeg args; `runner.py` – execution, progress, cancel;
    `runner.create()` returns a RifeRunner for RIFE jobs
  - `rife.py` – detect (test run, GPU name, software-only flag), exact-grid piece plan,
    RifeRunner: per piece ffmpeg → PNG → rife-ncnn-vulkan -n → PNG stream into one encoder
  - `preview.py` – one frame as BMP via ffmpeg (exact seek for the playhead, keyframe-only
    seek for thumbnails); trim rules live in `Job.trim_with_in/out`, `snapped_trim`
  - `testencode.py` – TestEncode (N output frames from the playhead into a temp dir), steady
    fps = frames / elapsed (see Hard-won details), Estimate for a clip: own test if settings
    are equal, else scaled by pixel count from another clip's test with equal settings
- `vsc/gui/` – PySide6. Start with `.venv/bin/python -m vsc.gui [CLIPS...]`.
  - `clips.py` – Clip (path, info, frames, settings, `ui` dict for widget-only choices such as
    resolution preset / aspect) and the table model
  - `workers.py` – QThreadPool tasks: probe + frame scan per clip, encoder detection
  - `info_panel.py`, `settings_panel.py` (widgets → OutputSettings → `_sync()` back to widgets),
    `timeline.py` (frame view, thumbnail timeline with keyframe ticks + draggable in/out,
    transport, shortcuts ←/→, Shift+←/→, Home/End, I/O), `main_window.py` (clip table on
    top; below, tabs "Preview & trim" / "Test encode" / "Clip info" next to the settings),
    `test_panel.py` (run/cancel, result + estimate, CompareView side by side / wipe)
  - `workers.FrameFetcher` – one decode at a time per view, latest request wins.
  - `zoom.py` – ZoomState (Fit / 100 % / 200 %, pan, double-click toggle) shared by FrameView
    and CompareView; at 1:1 the full-size frame is requested. In the comparison both pictures
    use the output's geometry (source fitted inside it) so the same region is shown.
  - Clip.trim / Clip.playhead are per clip and never copied by "apply to all".
  - Workers emit via `_emit()` – the window may be gone; Clip.removed stops thumbnail loaders.
  - Combo item data must not be a `Fraction` (Qt turns it into a float) – stored as `str`.
  - GUI tests run headless (`QT_QPA_PLATFORM=offscreen`, set in tests/test_gui.py).

## Hard-won details
- Lossless retime uses `-itsscale` with a 1e-11 upward bias (ffmpeg truncates scaled timestamps).
- Copy trimming seeks to the keyframe's exact time rounded *up* to µs (`-ss NNNus`); any offset
  from the frame grid gets scaled and produces 1-tick jitter. Out-point uses `-frames:v`
  (decode order = complete GOPs).
- Re-encode retiming uses `setpts=N/(rate)/TB` (frame-number based, immune to source jitter),
  then `fps=` / `framerate=` / `minterpolate=`. minterpolate needs `tpad=stop=2` to reach the end.
- Hardware test encodes can crash ffmpeg (system libva older than the static build) – always in
  a subprocess; only negative return codes / 0xC0000005 count as crashes.
- ProRes 4444 is reported as yuv444p12le by the decoder even if encoded from 10-bit.
- Dev machine: i7-8565U + Intel UHD 620, no working HW encoders (no CUDA, QSV runtime missing,
  VAAPI crash). minterpolate ≈ 1.2 fps at 1080p, x264 medium ≈ 35 fps.
- Time estimate = test frames / total test time. Checked against full encodes (4K + 1080p, x264):
  −8 … +19 % when the test piece is typical, −26 % on a clip whose test piece was easier than
  the rest. A "steady rate + start-up" model was 7–42 % too optimistic (x264 lookahead).
  Size estimate (bytes per test frame × frames) was within ~1.5 %.
- rife-ncnn-vulkan `-n n` on L files puts output i at i·L/n (clamped at the last file). Exact
  timing needs L·ratio integral → ratio rounded to a small denominator (≤ 0.05 % speed change),
  each piece has L = multiple of the denominator incl. look-ahead frames (see rife.py docstring).
- RIFE colour: YUV→RGB at extraction and RGB→YUV at encoding use the same explicit matrix/range
  (source colour_space, default bt601) – verified: RIFE output vs plain pipeline ≥ 37 dB PSNR.
- RIFE speed on Intel UHD 620: 2 fps @720p, 0.9 fps @1080p; temporal TTA (-z) 2×, spatial TTA
  (-x) 8× (not used). UHD mode (-u) only for frames ≥ 2560 px wide.
