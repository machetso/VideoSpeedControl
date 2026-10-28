# VideoSpeedControl – developer notes

Read SCOPE.md for the agreed feature set and milestone status.

## Resume here
- Status 2026-10-26: milestones 1–6 done and committed, plus the extensions below (one commit
  after milestone 6; 124 tests green as of 2026-10-28). The user has NOT tried most of it yet – next step is
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
  Version in `vsc/__init__.py` (0.9.1).
- Milestone 7 – packaging (in progress, 2026-10-26). User decisions: GitHub Actions, private
  repo, Inno Setup installer (per-user install, admin optional), build on tag `v*` + manual,
  AV2 NOT on Windows yet (later: build AVM with MSVC in the workflow).
  - `packaging/VideoSpeedControl.spec` (one-folder, data + vendor/<tool>/<platform>-x64 into
    `_internal/`, AVM only if present), `packaging/launch.py` (entry; `VSC_SMOKE_TEST=<file>`
    = headless self-check → report file, used by CI), `packaging/installer.iss`,
    `.github/workflows/windows.yml` (tests on Windows are report-only for now).
  - Linux bundle built + smoke-tested locally (563 MB incl. AVM). Linux packaging format
    (AppImage / tar.gz) not decided yet.
- 2026-10-27: Windows build confirmed working by the user. New (user request, committed
  5144974): .cst treatments, multi-step undo / redo of sections, batch entry
  double-click (edit / another encoding) with name-addition checkboxes – see Layout.
- Open option: enable Intel Quick Sync on the dev laptop (needs Intel media runtime / oneVPL).
- ANDROID – RESUME HERE (paused 2026-10-27 by the user): milestone 5 (re-encode) in progress.
  Next steps: (1) try the new Export card (Lossless / Re-encode switch, fps / speed / codec /
  quality / resolution) on the phone – install with `./gradlew installDebug`, open a synthetic
  clip via the VIEW intent (see below), take screenshots with `adb exec-out screencap -p`;
  (2) let the user re-test the real-time stutter with a Re-encode export; (3) milestone 6
  smart export. Speed status: re-encode of the 30 s Pixel clip ≈ 20 s (sound ≈ 5 s in an
  optimised build, 10 s in debug); `./gradlew installRelease` = optimised build signed with the
  debug key (debug builds are much slower at sound / pixel loops). Status table: android/PLAN.md.
- 2026-10-27: Android version started in `android/` – fully native (Kotlin + Compose, Media3 /
  MediaCodec / MediaMuxer), no FFmpeg / Python on the phone; `vsc/core` is the reference whose
  rules are ported. Plan, decisions and milestones: `android/PLAN.md`. Milestone 1 (skeleton,
  clip info, `Segments` port + unit tests) done and checked on the user's Pixel 10 Pro
  (Android 17 / API 37) against desktop ffprobe values.
  Build: `cd android && JAVA_HOME=~/Android/jdk ./gradlew testDebugUnitTest assembleDebug`.
  On-device tests: `android/tools/device_test.sh [CLIP…]` (pushes clips to /data/local/tmp/vsc,
  `TestClips` copies them into the app cache; missing clips are skipped). The user's clips are
  private: copy to the laptop only with permission, delete afterwards. A copy of
  PXL_20261025_152730266.mp4 (120 fps slow-mo) stays in /data/local/tmp/vsc on the phone.
  Synthetic clips: `android/tools/make_test_clips.sh` (desktop FFmpeg → /tmp/opencode/vsc-test);
  exports of them land in the app cache `cache/out/` → pull with
  `adb exec-out run-as com.alexvulcu.videospeedcontrol cat cache/out/X.mp4 > X.mp4`.
- Android milestone 2 (lossless retime + sections, video only) done 2026-10-27: verified with
  desktop ffprobe – packets bit-identical, borders exact, no jitter. Details:
  MediaExtractor → MediaMuxer (90 kHz MP4 time scale, ≤ 1 tick rounding); MediaExtractor
  gives µs → `FrameMap.exactTimes` uses the exact fps grid when every frame is on it (else
  1–11 µs jitter after scaling), phone clips with real jitter keep their own times.
  Output via MediaStore (pending until done) in Movies/VideoSpeedControl/. No foreground
  service yet (export dies if the app is killed) – milestone 7.
- Android milestone 3 (sound) done 2026-10-27, `core/Audio.kt`: decode → per span cut →
  Media3 `SonicAudioProcessor` (input rate × slow-mo factor = asetrate, tempo, → 48 kHz) →
  each span cut / padded to its exact length → AAC 192k in memory → interleaved in the same
  MediaMuxer pass. Pitfalls: Media3 1.11 needs `flush(StreamMetadata.DEFAULT)` (plain
  `flush()` throws); the AAC encoder's 2048-sample priming is dropped (else sound 43 ms late);
  MediaMetadataRetriever misses text capture-fps tags (FFmpeg / desktop exports) →
  `core/Mp4Meta.kt` reads mdta keys/ilst itself (moov/meta and moov/udta/meta, text or float).
  Verified with tone clips (zero crossings): pitch kept at 9.6× slower, slow-mo restored.
- Android milestone 4 (editor) done 2026-10-27. `core/ClipEdit.kt` (trim snapping, sections,
  undo / redo 200, unit-tested), `core/FrameSource.kt` (MediaMetadataRetriever: keyframe
  thumbnails + exact frame after 120 ms rest), `ui/` = EditorViewModel, Timeline (Canvas:
  strip, sections, trim, keyframe ticks, pending start, playhead; tap / drag), Panels,
  PreviewPlayer (ExoPlayer, speed = piece rate ÷ file fps, pitch = slow-mo factor, polled every
  16 ms; SILENT with sections – audio-clock buffering delays speed changes ~1 s). App accepts
  "Open with" / "Share" (VIEW / SEND video/*), which also lets tests open a clip via
  `adb shell am start -a android.intent.action.VIEW -d content://media/external/video/media/ID
  --grant-read-uri-permission -n com.alexvulcu.videospeedcontrol/.MainActivity` (synthetic
  clips pushed to /sdcard/Download/vsc-test + media scan; delete them afterwards).
  Measure playback with logcat timestamps, not uiautomator dumps (too slow / irregular).
- 2026-10-27 after user test (scrubbing / real-time preview stuttered): `core/Proxy.kt` = 480 px
  JPEG of every frame (≤ 12000, else every n-th), built after opening: MediaCodec → Surface →
  `core/GlFrameGrabber.kt` (SurfaceTexture, GPU scale + YUV→RGB, glReadPixels) → JPEG on
  3 threads; ~90 fps on the Pixel (getFramesAtIndex ~35, YUV→RGB in Kotlin ~45 – debug builds
  are slow at per-pixel loops). MediaCodec already applies the track rotation to its output
  surface – don't rotate again. Scrubbing shows the proxy frame at once, sharp frame after
  120 ms; thin progress bar in the timeline. Play preview: sections or > 2× file rate → proxy
  frames on an exact clock (silent); otherwise ExoPlayer with sound. Magnetic cursor
  (`ClipEdit.snap`, 12 dp, 🧲 chip, stored), jog = drag on the picture (1 frame / 8 dp).
- Android milestone 5 core (2026-10-27): `core/Reencode.kt` – codecs in ASYNC callback mode
  (sync polling costs a media-server round trip of 1–4 ms per call → 2–4× slower; `Audio.kt`
  decoder / AAC encoder are async too), decoder → `GlFrameGrabber(w, h, encoderSurface)` →
  `present(ptsNs)`; source frame f is drawn for every output tick in [ceil(t(f)·fps),
  ceil(t(f+1)·fps)). `Job.kt`: `Timing` interface (LosslessJob, ReencodeJob), `VideoCodec`,
  `Quality` (bits per pixel), sizes rounded to the nearest even number. Output tagged BT.709.
  Synthetic test clips are BT.709-tagged: untagged HD is BT.601 for FFmpeg but BT.709 for
  Android (looked like wrong colours). Frame check: `android/tools/verify/check_frames.py` (run in /tmp/opencode/vsc-test)
  (output frame k vs expected source frame, MSE of neighbours) – all 810 frames exact, MSE ≈ 1.
  `TestClips` re-copies a clip when its size on the phone changed.

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
    "Clear sections" (right edge, asks first). Every section edit goes through
    `Clip.edit_segments(new, what)` → per-clip `undo_steps` / `redo_steps` (200), buttons
    "↶ Undo" / "↷ Redo" (Ctrl+Z, Ctrl+Shift+Z / Ctrl+Y) with the step in the tooltip.
    Double-click in the batch list (`ExportPanel.open_entry`) → `MainWindow._open_entry`:
    `batch_dialogs.ask_entry_action` NEW / EDIT, loads settings + `BatchEntry.ui` + trim +
    sections; EDIT shows "✔ Update batch entry" (`_editing`, ends on clip switch / removal).
    "Add to batch" for a clip already in the list → `AdditionDialog` (checkboxes from
    `batch.ADDITIONS`, stored in QSettings "batch/additions") → `BatchEntry.additions`,
    appended to the pattern name by `batch.plan(..., additions)`.
    Successful batch-list exports set `BatchEntry.exported`; `done` = that file still exists.
    `_plan` plans only not-done entries; done ones become `Item(done=True)` (shown green,
    skipped by `Batch.run` without a result); "Update batch entry" clears `exported`.
  - Treatments (.cst): `core/treatment.py` (JSON; fingerprint = size + SHA-256 of first /
    middle / last MiB; `check()` also compares the frame count). Toolbar "Load / Save
    treatment…" (Ctrl+L / Ctrl+S), .cst via drop / Add files → `MainWindow.open_treatment`:
    current clip, any clip in the list, else the saved path / same name next to the .cst
    (added, applied in `_scanned` via `_pending`). Mismatch → refused.
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
- Smart analysis (2026-10-28, user review): `scan_frames` keeps packets in decode order with
  `pos` / `size` (`FrameMap.packets`) – parse ffprobe as key=value, it prints fields in its own
  order (pts, dts, size, pos, flags), not the requested one. `join_points` then reads only the
  NAL headers of the keyframe packets (+ the packet after each, RASL check) straight from the
  MP4 / MOV file: 1 ms instead of two extra full passes (ffprobe again + whole bitstream
  through a pipe). Fallback (other containers): `parse_access_units` (pure, unit-tested on
  synthetic Annex-B split at every byte) over FFmpeg's output. FFmpeg / ffprobe failures raise
  `smart.AnalysisError` – a truncated stream used to look like "only frame 0 is safe".
- Sound sync (2026-10-28): rubberband as FFmpeg runs it moves content ~10–18 ms of INPUT
  time early (87 ms at 8× slower, 720 ms at 40×), and stretched pieces come out short
  (−56 ms at 8×) – both used to add up over sections (−55 … −300 ms, also in later real-time
  parts). Now: `audio.rubberband_lead(tempo)` measures the onset of a click through the same
  filter (cached), every piece is its own `-ss/-t` input with 0.5 s context (no asplit → no
  buffering of later pieces), trimmed by the lead and cut / padded to its exact length in
  samples from the running total. Real-time parts exact (±0.5 ms); stretched parts: onset
  −10 … +40 ms (up to ~+75 ms at 40×, content-dependent, late side – tolerable). 40× smears a
  click over ~250 ms, so tests time the onset, not the peak. Slow-mo restore = aresample 48k,
  asetrate 48k·k, aresample 48k – no need to know the source rate (was assumed 48 kHz).
  Smart: sound pieces of re-encoded parts scaled to the part's whole-frame duration.
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
