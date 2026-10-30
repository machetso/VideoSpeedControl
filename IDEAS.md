# Ideas for future versions

Collected while building the desktop and Android versions. None of this is planned or promised –
the agreed feature set is in SCOPE.md (desktop) and android/PLAN.md (Android). Each entry notes
why it was postponed and what is already known.

## Picture

- **Flicker / exposure correction for re-encoded parts** (both). Phone slow-mo recordings can
  contain short auto-exposure jumps: in PXL_SloMoTest.mp4 six frames at 240 fps (25 ms) are
  +38 brightness levels brighter, six others −38 darker – invisible in real time, a visible
  flash in slow motion. Idea: detect frames whose mean brightness jumps for a few frames and
  then returns, and match them to their neighbours (desktop: FFmpeg `deflicker`; Android: a gain
  in the GL step). Must not flatten real light changes (flash, a lamp switched on) – only short
  jumps that return. Impossible in copied parts of lossless / smart exports (they are not
  decoded); there the part would have to be re-encoded. Postponed by the user (2026-10-28).
- **Frame blending / interpolation on Android** for re-encoded parts that play slower than the
  output frame rate (now: frames are repeated). Blending is cheap in the GL step; optical flow
  (RIFE) stays desktop-only for now.
- **HDR / 10-bit** (Android): re-encode currently outputs SDR 8-bit, the smart export refuses
  HDR sources. Needs a Main10 encoder configuration, 10-bit GL path and HLG / PQ metadata.
- **Constant-quality encoding** (Android): re-encode uses VBR with a bitrate from bits per pixel
  (High = 0.14). If the Pixel encoder supports BITRATE_MODE_CQ, a quality level would adapt
  better to the content.
- **More resize options** (Android): only "fit, keep aspect" now; the desktop also has exact
  size with pad / crop / stretch and scaler choice.

## Smart export

- **Same automatic rule on the desktop**: Android re-encodes every part whose playback rate
  differs from the output frame rate (one switch + ticks per part); the desktop still marks
  sections one by one. Both write the same .cst sections, so this is only a UI change.
- **Fewer re-encoded frames**: re-encoded parts are widened to the nearest safe keyframes, which
  eats into neighbouring copied sections. A magnet / snap of section borders to keyframes (in
  smart and lossless mode) would keep more frames untouched.
- **Apple devices**: Android writes `hvc1` with parameter sets in-band (MediaMuxer cannot write
  `hev1`); the desktop writes `hev1` / `avc3`. Neither plays on Apple devices. Options: a
  custom MP4 muxer (e.g. Media3's Mp4Muxer) or re-encoding the whole clip for Apple.
- **HDR sources** – see Picture.

## Sound

- **Alternatives to pitch-kept stretching** (both): play slow-motion parts lower like a slowed
  tape (no artefacts at all, dramatic), mute them, or lower their volume. Offered as a choice
  and declined by the user for now (2026-10-28: "keep Sonic, no choice").
- **Other stretching algorithms** were compared by ear (2026-10-28) and not taken: rubberband
  (FFmpeg filter), Rubber Band R3 offline, Signalsmith Stretch (MIT). Facts if this is reopened:
  FFmpeg's rubberband moves content 10–18 ms of input early (720 ms at 40× slower); waywardgeek's
  C Sonic drifts at slow speeds and clamps at 20×; Media3's Sonic (now on both platforms,
  bit-exact) does neither.
- **Sound in the Android play preview with speed sections**: silent now, because ExoPlayer's
  audio clock applies speed changes about a second late. A separate AudioTrack fed by our own
  Sonic stream, paced by the proxy clock, could play it in sync.

## Android app
- **PLANNED (accepted by the user 2026-10-30, not built yet): preview cache.**
  - The scrubbing proxy (and the frame list, the smart keyframe analysis, the timeline
    thumbnails) is stored per video, keyed by the .cst fingerprint (renamed / moved files still
    match, a changed file does not) – never inside the video (originals are read-only).
  - Stored in chunks from keyframe to keyframe, each with a CRC; a broken / missing chunk is
    rebuilt alone from its keyframe; chunks are written while the proxy is built, so an
    interrupted build continues.
  - Where: proxies in the app's private storage (invisible, removed on uninstall); .cst files in
    `Documents/VideoSpeedControl/Clip Speed Treatments/` – "Save" writes there directly (no file
    dialog), "Share" for other places.
  - Clean-up: a preview stays while its video is open, in the batch list, or has a .cst in that
    folder; the others are deleted – not before the app has run 2 minutes, and postponed while
    an export, proxy build or keyframe analysis runs (check every 30 s). Cap 2 GB: oldest
    previews without a .cst go first, those with a .cst last.
  - Format: JPEG quality 60 instead of 75 (measured on the Pixel, 480×270: JPEG q75 22.1 KB /
    2.3 ms encode / 0.8 ms decode, JPEG q60 17.0 KB / 1.1 ms / 0.7 ms, WebP q60 12.9 KB /
    13.7 ms / 1.4 ms – WebP would slow the ~90 fps build down; ProxyFormatDeviceTest).
- **Proxy as a small video** (hardware-encoded, keyframe every chunk): probably 5–10× smaller
  than JPEGs, but every jump decodes part of a chunk – slower scrubbing, much more work. Only if
  the cache size becomes a problem.

- **Faster proxy build**: ~90 fps on the Pixel (decoder → GPU → JPEG); asynchronous codec mode
  and several frames in flight might double it.
- **Faster re-encode**: ~50–75 fps at 1080p; the decode → GL → encode chain is still one frame at
  a time.
- **German user interface**: all texts are English (as on the desktop); Compose string resources
  would allow translations.

## Desktop app

- **Windows build of Sonic**: the GitHub workflow builds the library with the runner's MinGW gcc
  – not tried yet; check the "Build Sonic" step on the next Windows build.
- **Sound in the play preview**: the desktop preview is silent too.
