# Changelog

All notable changes to VideoSpeedControl – the desktop app (Linux / Windows, Python) and the
Android app (native Kotlin). Entries marked *(Android)* or *(desktop)* concern one of them only.

## 0.93 – not released yet

Mobile UX and further tests still to come before the release.

### Stored previews (both)
- The scrubbing proxy, the timeline thumbnails, the keyframe analysis of smart re-encode and
  (desktop) the frame list are **stored per video** – a clip opened again is ready almost at
  once (Android: proxy 26 ms instead of 4–10 s). Recognised by the content fingerprint of the
  .cst files, so renamed or moved files still match.
- Stored in **chunks from keyframe to keyframe**, each with a checksum: a damaged or missing
  chunk is rebuilt alone (the pictures are identical to a full build), and an interrupted build
  continues where it stopped.
- **Clean-up**: a preview stays while its video is open / in the clip list, in the batch list,
  or has a Clip Speed Treatment; the others are deleted – not before the app has run 2 minutes
  and only while no export, preview build or analysis runs (retried every 30 s). Cap 2 GB, the
  least recently used without a .cst first.
- Where: Android – the app's private storage; desktop – ~/.cache/VideoSpeedControl/previews
  (Windows %LOCALAPPDATA%\VideoSpeedControl\previews).
- **Clip Speed Treatments** live in *Documents/VideoSpeedControl/Clip Speed Treatments*:
  Android "Save" writes there directly (no file dialog), "Load" starts there; the desktop offers
  it as the default folder and also keeps the previews of .cst files saved elsewhere.
- *(Android)* **Interface languages**: English, German, Spanish, French, Romanian, Hebrew
  (right-to-left; timeline and transport stay left-to-right) and – for fun – Klingon, chosen in
  the menu behind the logo ("Language / Sprache"); default is the phone's language if there is a
  translation, the choice is kept. Numbers and plural forms follow the language. One dictionary
  per language in `i18n/<code>.json` (for the desktop later too) – a new language is a new file.
- *(Android)* **Menu behind the logo**: Easy / Pro with what each mode can do, the folders
  (saved videos, Clip Speed Treatments – each with "Open"), the space the previews take and
  "Delete previews".
- *(Android)* Preview pictures as JPEG quality 60 (smaller, twice as fast to make; WebP was
  measured and is 6–12× slower to encode on the phone).

### Easy / Pro
- **Easy / Pro switch** (Easy is the default). Easy hides the codec details: smart re-encode
  always uses the source codec, re-encode always AV1 (fast), each with the codec's default
  preset, quality and chroma. Desktop: switch at the top of the output settings; switching to
  Easy applies to all clips. Android: switch in the export card and a tappable Easy / Pro badge
  next to the app name.
- **Easy smooths every speed change** automatically (0.5 s); the per-border "Smooth in / out"
  switches exist only in Pro.
- *(Android)* Easy shows much less:
  - Speed sections are called **Clip Sections** (both modes); a section shows as
    "Section 1: ⏳ 5.0 s" with its **Video speed** ("4× slower", "9.6× slower (original)",
    "real time") instead of frame numbers and frame rates. The speed list has whole frame rates
    only (30, not 29.97), the original and real time – every entry once.
  - No "Start = playhead / End = playhead", no explanations, no "Last change", no frame /
    source / output line, no keyframe buttons; timeline labels show the speed.
  - No trim card: the **yellow trim brackets** on the timeline (both modes, draggable, reaching
    above the strip) and an "In · Out · ⏳ length" line under the timeline.
  - **Whole clip**: one speed for the whole clip, the sections set aside ("Whole clip selected");
    switching on / off and its speed are undoable.
  - Smart: one-sentence description, automatic rule only (no switch, no part list, no codec /
    size notes). Re-encode: no codec line.
  - **Save** instead of Export: "Save video", "Save all (n)", "Add as new version" (no
    "update entry" button in Easy). Pro: "✔ Save changes to this entry" (was "Update batch
    entry").
  - "Video speed of new sections" is hidden while a section is open.
- *(Android)* Chosen options are green (Easy / Pro, Lossless / Smart / Re-encode, switches that
  are on).

### Editing
- Choosing **smart re-encode** pre-selects every section whose frame rate differs from the
  output frame rate (desktop: its output frame rate) for re-encoding.
- Switching from smart to **re-encode** selects AV1 (fast) again.
- Transport symbols are drawn instead of font glyphs: |◀ and ▶| with the bar centred, keyframe
  buttons "− 🔑" and "🔑 +" close together.
- *(Android)* The Clip Sections explanation (Pro) describes the quick section end correctly.

### Export
- *(Android)* **"Still saving … n %"** while a video is written (export card, batch list,
  notification); the file stays hidden (`.pending-…`) until it is complete.
- *(Android)* Sound for smooth transitions: the steps of a ramp share one stretched sound
  span – lossless exports with smooth transitions render about twice as fast.
- *(Android)* Batch list: tidy rows – a picture of the video and its mode (Lossless / Smart /
  Re-encode) only; file name, settings and result behind an ⓘ button; green play symbol (grey
  when the file is gone); "Open folder" buttons next to the batch list and the finished export.
- **48 fps** as an output frame rate (everywhere a frame rate can be chosen).
- *(Android)* Re-encode: "Output frame rate" (no "constant"), resolution "No change (W×H)".
  Easy: shorter lossless description, sound is just the switch, "Output frame rate" with plain
  rates (lossless too), no re-encode speed choice (the speed comes from the clip sections).

### Other
- *(desktop)* Laptop launcher uses a themed icon (`videospeedcontrol`) so the new logo shows.
- *(Android)* Device tests for diagnosing output files and timing exports.

## 0.92 – 2026-10-29

### New logo
- New logo (`assets/VSL-Logo_transparent.webp`) for all variants: desktop icons (16–512 px,
  Windows `.ico`), About picture, PDF title page; Android adaptive launcher icon on a dark blue
  gradient, title-bar logo, monochrome / notification gauge symbol.

### Speed sections
- **Quick section end**: without a marked start, a section starts right after the section
  before it (inside a section: that section's start – it is split; otherwise the clip / trim
  start).
- **Draggable borders**: borders between sections are drawn clearly (white line with a grip)
  and can be dragged; the neighbouring sections follow, the picture shows the border frame, one
  drag is one undo step.
- **Editing a section**: select it (timeline or list / table), then change its rate, set its
  start / end to the playhead, remove it.
- **Smooth transitions** per border ("Smooth in / out"): the speed changes evenly over 0.5 s of
  output, centred on the border, played as 10 steps; exact fractions, so desktop and Android
  compute the same frames. Stored in `.cst` files (`smooth_start` / `smooth_end`).
- **Undo / Redo** buttons show how many steps are possible.
- Transport: first / last frame, previous / next keyframe with a key symbol, "◀ 1" / "1 ▶";
  the ±10 frame buttons are gone *(Android)*.

### Export
- **AV1 (fast)** is the default codec for re-encoding (desktop: SVT-AV1, x264 if FFmpeg lacks
  it). *(Android)* New codecs **AV1 (fast)** (hardware encoder) and **AV1 (best quality)**
  (software encoder, highest effort).
- "Treatment" is now called **Clip Speed Treatment** (`.cst`) everywhere.
- *(Android)* "▶ Play" after an export is a filled button; batch list play symbol; "Open folder".

### Android app (first version, milestones 1–7)
- Native Kotlin / Compose app (Media3, MediaCodec; no FFmpeg on the phone) with the desktop's
  rules and the same `.cst` files: clip info, lossless retime with speed sections, sound with
  pitch kept (Sonic), timeline with thumbnails, exact scrubbing and play preview, re-encode
  (H.264 / HEVC / AV1), smart export (only differing parts re-encoded, source codec), batch
  list surviving restarts, export in a background service with notification, own clip gallery
  (camera recordings newest first, real file names), "＋ Clip" button.

### Desktop
- Sound stretching with Sonic (a C port of Media3's Sonic, bit-exact with the Android app)
  instead of rubberband.
- Smart export: faster join point analysis, encoder gets the source's colour description (no
  flashes at the joins), fixes from a code review (return codes, sound drift, sound length of
  re-encoded exports).
- User guide and screenshots updated.
