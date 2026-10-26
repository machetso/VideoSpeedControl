# VideoSpeedControl – developer notes

Read SCOPE.md for the agreed feature set and milestone status.

## Resume here
- Status 2026-10-26: milestones 1–6 done and committed, plus the extensions below (one commit
  after milestone 6, 98 tests green). The user has NOT tried most of it yet – next step is
  their own test round (list in the 2026-10-26 conversation: export tab, speed sections,
  smart re-encode in VLC / on a phone, batch list, scrubbing / magnet, AV2, a GoPro clip).
- Extensions after milestone 6 (all user requests):
  - Clip info: device / recorded / audio; phone slow-mo: `MediaInfo.real_fps` = capture rate
    is the "original" – speeds refer to it, timestamps and seeking still use `fps`.
  - Frame rate drop-down with "N× slower, length" and "(original)"; 120 fps preset.
  - Processing radio "Lossless / Smart re-encode / Re-encode" (derived from the settings:
    `smart` → Smart, codec copy → Lossless, else Re-encode; `set_process()` forces each).
  - "▶ Play preview" (Space), fast scrubbing (proxy copy), magnetic cursor (🧲).
  - Speed sections (`core/segments.py`): lossless = VFR via setts, re-encode = constant fps;
    rates down to 23.976 and up to 8× the original. Smart re-encode (`core/smart.py`):
    marked sections re-encoded with the source codec, rest copied, joined (H.264 / HEVC).
  - AV2 via AVM reference software (`core/avm.py`, `tools/fetch_avm.py`), Linux only.
  - Batch list ("➕ Add to batch" snapshots), "Clear sections" with confirmation + undo.
  - Desktop launcher (see Setup).
- 2026-10-26: artwork, docs, open source (user request): `assets/*.webp` (user's artwork; the
  .jpeg / .psd next to them in the root are the user's and not committed) → `tools/make_icons.py`
  → `vsc/gui/resources/` (icons 16–512, icon.ico, splash.webp = About picture; no splash at start
  – user removed it). "Help" button with menu at the right end of the toolbar (F1 guide, PDF,
  About), code in `vsc/gui/help.py`. Guide = `vsc/docs/manual.md` (+ images from
  `tools/build_docs.py --screenshots`, synthetic Mandelbrot clip – no private footage) → PDF.
  MIT LICENSE, header in every .py, README "License & Attribution", THIRD_PARTY_NOTICES.md.
  Version in `vsc/__init__.py` (0.9.0).
- Milestone 7 – packaging (in progress, 2026-10-26). User decisions: GitHub Actions, private
  repo, Inno Setup installer (per-user install, admin optional), build on tag `v*` + manual,
  AV2 NOT on Windows yet (later: build AVM with MSVC in the workflow).
  - `packaging/VideoSpeedControl.spec` (one-folder, data + vendor/<tool>/<platform>-x64 into
    `_internal/`, AVM only if present), `packaging/launch.py` (entry; `VSC_SMOKE_TEST=<file>`
    = headless self-check → report file, used by CI), `packaging/installer.iss`,
    `.github/workflows/windows.yml` (tests on Windows are report-only for now).
  - Linux bundle built + smoke-tested locally (563 MB incl. AVM). Linux packaging format
    (AppImage / tar.gz) not decided yet.
- Open option: enable Intel Quick Sync on the dev laptop (needs Intel media runtime / oneVPL).

## Setup
- Git: local repo, branch main. `.venv/`, `vendor/`, `tests/media/` are not committed –
  recreate with the setup steps below (tests regenerate their media).
- venv: `.venv/` (created with `--without-pip` + get-pip.py, because python3-venv/ensurepip is
  not installed system-wide). Run things with `.venv/bin/python`.
- FFmpeg: `python tools/fetch_ffmpeg.py [linux|windows]` → `vendor/ffmpeg/<platform>-x64/`.
  `vsc/core/ffmpeg_bin.py` prefers the bundled copy, then `VSC_FFMPEG_DIR`, then PATH.
- AVM (AV2 reference, v1.0.0): `python tools/fetch_avm.py` clones + builds avmenc/avmdec into
  `vendor/avm/linux-x64/` (needs git, cmake, nasm – installed via apt on the dev laptop;
  ~7 min). `VSC_AVM_DIR` overrides. AV2 tests are skipped without it.
- RIFE: `python tools/fetch_rife.py [linux|windows]` → `vendor/rife/<platform>-x64/`
  (rife-ncnn-vulkan 20221029 + rife-v4.6 model only; `VSC_RIFE_DIR` overrides). Tests that need
  it are skipped when RIFE / Vulkan is unavailable.
- Tests: `.venv/bin/python -m pytest tests -q` (test clips are generated into tests/media;
  shared fixtures in tests/conftest.py).
- Launcher (dev laptop, COSMIC): `~/.local/share/applications/videospeedcontrol.desktop`
  (+ copy in ~/Schreibtisch) runs `.venv/bin/python -m vsc.gui %F` in the project dir; icon
  `vsc/gui/icon.svg`, `setDesktopFileName("videospeedcontrol")` so Wayland matches it.
- CLI: `.venv/bin/python -m vsc info CLIP`, `... encode CLIP -o DIR --fps 25 [--codec x264 ...]`.

## Layout
- `vsc/core/` – no Qt imports; GUI-independent and testable.
  - `probe.py` – MediaInfo (ffprobe) and FrameMap (packet scan: exact pts, keyframes).
    Recording metadata from container tags: device (Android / Apple make+model, GoPro via
    handler_name + `firmware` prefix → GOPRO_MODELS, else a non-Lavf `encoder` tag, e.g. DJI),
    recorded time (Apple creationdate with offset, else creation_time; GoPro writes local
    time marked as UTC), `com.android.capture.fps` → `slowmo_factor` (phone slow-mo files
    play at ~30 fps), first audio track
  - `formats.py` – catalogue: fps, resolutions, chroma, scalers, interpolation, codecs + UI texts
    Quality is shown as named levels (`QUALITY_LEVELS`, per-codec values in `QUALITY_VALUES`,
    "High" = the codec's old default) + "Custom…" (`ui["quality"]`, reset on codec change);
    presets get descriptions from `preset_label` (CineForm's "preset" is a quality level).
  - Settings panel must fit ~345 px (half-screen window): drop-downs are `settings_panel.Combo`
    (shrink, popup shows full texts), side-by-side pairs are stacked, info labels wrap.
  - `encoders.py` – encoder detection, pix_fmt lists, hardware test encodes (cached in
    ~/.config/VideoSpeedControl/encoders.json per FFmpeg version)
  - `job.py` – OutputSettings (per clip), Trim, Job (mode decision, sizes, formats)
  - `command.py` – Job → ffmpeg args; `runner.py` – execution, progress, cancel;
    `runner.create()` returns a RifeRunner for RIFE jobs
  - `rife.py` – detect (test run, GPU name, software-only flag), exact-grid piece plan,
    RifeRunner: per piece ffmpeg → PNG → rife-ncnn-vulkan -n → PNG stream into one encoder
  - `preview.py` – one frame as BMP via ffmpeg (exact seek for the playhead, keyframe-only
    seek for thumbnails); trim rules live in `Job.trim_with_in/out`, `snapped_trim`
  - `batch.py` – name pattern (`render_name`, tokens), `plan()` (output folder or next to the
    source, policy rename / overwrite / skip; names unique within the batch, a source is never
    overwritten), `Batch.run()` one item after another, cancel; incomplete outputs are deleted
  - `playback.py` – PlayPlan: ffmpeg decodes at ≤ 960×540, retimes like the export, raw RGB to
    a pipe; mci / RIFE shown as `framerate` blending; fast decode flags above 100 src fps
  - `avm.py` – AV2: FFmpeg has no AV2 at all (9.0.2), so `command.decode_args` (ffmpeg: trim,
    retime, scale) pipes y4m (stdout) into avmenc (IVF / WebM); ffmpeg's `-progress` goes to
    stderr (`pipe:2`) – portable, no extra fds. `decode_for_preview` (avmdec → FFV1 MKV) lets
    the test comparison read AV2. Detection is never cached. Test encodes are capped at
    `EXTERNAL_MAX_FRAMES` (5). RIFE + AV2 is refused (RifeRunner encodes with ffmpeg).
  - `smart.py` – smart re-encode. `join_points` reads NAL types from the Annex-B stream (in
    the clip loader thread, after the frame scan → `Clip.joins`): safe = IDR, or CRA without
    RASL after it (x265 default = open GOP → only frame 0 is safe → everything re-encoded).
    `Clip.job` passes a FrameMap whose keyframes are the joins, so all snapping uses them.
    `plan` widens re-encoded sections to joins; parts → MPEG-TS (headers in-band), concat
    demuxer with exact `duration` lines → MP4 tag hev1 / avc3 (Apple can't play) or MKV.
    Encoded parts: source codec, `-noautorotate`, one closed GOP, repeat-headers; rotation
    is set again on the join (`-display_rotation`, same sign as probe).
  - `audio.py` – sound (toggle button "🔊 Sound on / 🔇 Sound off" under Processing, setting
    `OutputSettings.audio`): `runner.create` wraps any video runner in `AudioRunner` when
    `audio.wanted(job)` (setting `audio`, clip has sound, container takes it, not AV2): video →
    temp file, then one ffmpeg pass adds the sound (video copied, MP4 tag kept – hvc1 / hev1).
    Phone slow-mo sound is stored like a slowed tape (Pixel: nothing above ~3 kHz) →
    `asetrate` × slow-mo factor first; then per speed piece `atrim` + rubberband (pitch kept),
    concat, apad/atrim to the video length. Tests check pitch with pure tones (zero crossings).
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
    `test_panel.py` (run/cancel, result + estimate, CompareView side by side / wipe),
    `export_panel.py` (tab "Export": options stored in QSettings, planned queue, progress)
  - Batch list: "➕ Add to batch" (preview tab) appends a `BatchEntry` (main_window: clip, job
    snapshot, label from `batch.describe`) – the same clip can be added several times;
    export scope "Batch list" exports those snapshots (list kept after export; entries of
    removed clips are dropped). `{mode}` name token = lossless / smart / reencode.
    Section table: rebuilt on change, keeps its scroll position; new / edited row is scrolled
    into view (`_show_row`). Last chosen output fps = default for new sections
    (QSettings "sections/out_fps", else 30).
    "Clear sections" (right edge, asks first) keeps the old list for "↶ Undo" / Ctrl+Z until
    sections are edited.
  - Export: jobs are snapshots taken at start (settings / trim edits don't affect a running
    batch); Remove / Clear are disabled while it runs; Clip.export is shown in the Status
    column; the plan is refreshed on any change and when a tab is switched.
  - `workers.FrameFetcher` – one decode at a time per view, latest request wins.
  - Scrubbing: `workers.ProxyLoader` (one clip at a time, after the frame scan) fills
    `Clip.proxy` with a 384×216 JPEG per frame (every n-th above 12000 frames; Pixel clip:
    13 s, 25 MB). `PreviewPanel._request_frame` shows it at once (~1 ms, else the nearest
    thumbnail), `fetcher.supersede()`, and asks for the sharp frame after 120 ms of rest.
  - Magnetic cursor (`Timeline._snap`, 8 px, toggle 🧲 stored in QSettings): before a
    section start is marked it snaps to the frame after a section, while marking an end to
    the frame before the next section.
  - `workers.Player` – thread reads the pipe and paces frames by the clock; late frames are
    skipped (≥ 25 shown/s) and flagged "behind". Any `PreviewPanel.refresh()` stops playback.
    Labels whose text changes during playback have a horizontal `QSizePolicy.Ignored` (else
    the splitter / window re-layouts, the view resizes and triggers frame fetches → stutter);
    labels update at most every 0.1 s while playing.
  - `zoom.py` – ZoomState (Fit / 100 % / 200 %, pan, double-click toggle) shared by FrameView
    and CompareView; at 1:1 the full-size frame is requested. In the comparison both pictures
    use the output's geometry (source fitted inside it) so the same region is shown.
  - Clip.trim / Clip.playhead are per clip and never copied by "apply to all".
  - Workers emit via `_emit()` – the window may be gone; Clip.removed stops thumbnail loaders.
  - Combo item data must not be a `Fraction` (Qt turns it into a float) – stored as `str`.
  - GUI tests and tools run headless: `QT_QPA_PLATFORM=offscreen` is FORCED (the desktop session
    sets `wayland;xcb` – setdefault would open real windows on the user's screen). QSettings
    are redirected to a temp dir there.

## Hard-won details
- Lossless retime uses `-itsscale` with a 1e-11 upward bias (ffmpeg truncates scaled timestamps).
- Copy trimming seeks to the keyframe's exact time rounded *up* to µs (`-ss NNNus`); any offset
  from the frame grid gets scaled and produces 1-tick jitter. Out-point uses `-frames:v`
  (decode order = complete GOPs).
- Re-encode retiming uses `setpts=N/(rate)/TB` (frame-number based, immune to source jitter),
  then `fps=` / `framerate=` / `minterpolate=`. minterpolate needs `tpad=stop=2` to reach the end.
- Speed sections without re-encoding: setts sees packet timestamps relative to the seek point
  (with `-ss`) or absolute (without), so the expression uses `PTS-STARTPTS`; each piece is
  linear between its exact border times. Checking such VFR files with `ffmpeg -f null`
  warns about dts – an artefact of the null muxer's guessed time base; use
  `-fps_mode passthrough -enc_time_base:v demux`.
- Smart join pitfalls found by experiment: plain concat of hvc1 parts → the decoder uses the
  first part's headers for all (Pixel stores VPS/SPS/PPS only in hvcC) → 2/3 of frames broken.
  MPEG-TS parts + hev1 fixed it (copied frames bit-identical, framemd5). MP4 part durations
  from ffprobe were off by a frame → use the plan's own durations in the concat list.
- Hardware test encodes can crash ffmpeg (system libva older than the static build) – always in
  a subprocess; only negative return codes / 0xC0000005 count as crashes.
- ProRes 4444 is reported as yuv444p12le by the decoder even if encoded from 10-bit.
- Dev machine: i7-8565U + Intel UHD 620, no working HW encoders (no CUDA, QSV runtime missing,
  VAAPI crash – `-hwaccel vaapi` decoding crashes the same way). Preview decode of 1080p HEVC
  (Pixel): ~130 fps, ~175 fps with `-flags2 fast -skip_loop_filter all` → 240 fps real time
  can't keep up, 60 fps and below can. minterpolate ≈ 1.2 fps at 1080p, x264 medium ≈ 35 fps.
- AVM v1.0.0 speed on the dev laptop (8 threads, cpu-used 9, qp 140): 1080p ≈ 75 s/frame,
  360p ≈ 23 s/frame; `--lag-in-frames=0 --enable-tpl-model=0` → 17 s/frame but +24 % size
  (not used). Builds with cmake + nasm in ~7 min, links only libc/libm/libstdc++.
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
