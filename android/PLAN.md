# VideoSpeedControl for Android – plan

Agreed with the user on 2026-10-27.

## Decisions
- **Fully native app: Kotlin + Jetpack Compose, video work with Android's own media APIs.**
  No FFmpeg, no Python on the phone (an FFmpeg / Chaquopy route was started and dropped the same
  day: phone hardware encoders are far faster and lighter on the battery than software x264 /
  x265, the app stays small and there are no GPL obligations).
- The desktop Python core (`vsc/core/`) is the **reference**: its rules (speed sections,
  pieces, trim, naming, .cst format, phone slow-mo handling) are ported to Kotlin with the same
  semantics, and the tests port along with them. The desktop app is not changed.
- Code lives in `android/` in this repository.
- Test device: the user's **Google Pixel 10 Pro** (Android 16, arm64) via USB debugging.
  minSdk 30 (Android 11), targetSdk 36, compileSdk 37.2.
- Toolchain without root in `~/Android` (JDK 21, SDK): `android/tools/setup_toolchain.sh`.
- Package / application ID `com.alexvulcu.videospeedcontrol` (can still be changed until a
  first release).

## Android building blocks
| Task | API |
|---|---|
| Clip info, frame map (exact pts, keyframes) | `MediaExtractor` (sample time + sync flag per sample), `MediaFormat`, `MediaMetadataRetriever` (capture frame rate = phone slow-mo, rotation, device, date) |
| Lossless retime, speed sections (VFR) | `MediaExtractor` → `MediaMuxer`, every sample copied with a new presentation time (piecewise linear between section borders, like `segments.setts_expr`) |
| Audio, pitch kept | decode → Media3 `SonicAudioProcessor` (tempo per piece; slow-mo sound first restored to real pitch) → AAC encode (`MediaCodec`) → muxed with the video |
| Re-encode (constant fps, resize, frame-exact trim) | Media3 `Transformer`: `EditedMediaItem` with `SpeedProvider` (sections), `FrameDropEffect` (output fps), `Presentation` (size); H.264 / HEVC hardware encoders |
| Smart re-encode | marked sections decoded + encoded with `MediaCodec` in the source codec, other samples copied, all into one `MediaMuxer` track. Risk: one set of codec headers per MP4 track (the desktop pitfall with Pixel HEVC) – needs an experiment on the phone before it is promised. |
| Preview / scrubbing / play preview | `MediaMetadataRetriever.getFrameAtIndex` / thumbnails; Media3 ExoPlayer with the same `SpeedProvider` for play preview |
| Files | system photo picker (no storage permission needed); output via `MediaStore` into `Movies/VideoSpeedControl/`, so it shows up in Google Photos |
| Long exports | foreground service with progress notification |

## Scope of the first version
In: lossless retime, speed sections (VFR), phone slow-mo detection + pitch-corrected audio,
re-encode H.264 / HEVC (hardware), smart re-encode (if the experiment works), batch list,
.cst treatment files compatible with the desktop (same JSON, same fingerprint – a clip prepared
on the phone can be finished on the PC and vice versa).

Out (desktop only): RIFE / interpolation, AV2, ProRes / DNxHR / CineForm / lossless codecs,
test encode + comparison view.

## Milestones
(Ideas beyond these: ../IDEAS.md)
1. ✅ App skeleton + clip info: pick a clip, show container / codec / resolution / frame rate /
   slow-mo factor / keyframes / audio. Kotlin port of `segments.py` with unit tests.
2. ✅ Lossless retime + speed sections → MP4 in Movies/VideoSpeedControl, checked on the phone
   and with the desktop's ffprobe (exact timestamps).
3. ✅ Audio: slow-mo pitch restore + tempo per piece, muxed into the lossless output.
4. ✅ Timeline UI: thumbnails, playhead, trim, mark sections, frame rate per section, undo /
   redo, play preview; after user feedback: proxy frames (exact scrubbing, smooth preview),
   magnetic cursor, jog on the picture, proxy progress bar.
5. ✅ Re-encode – own GL pipeline instead of Media3 Transformer (constant fps with exact frame
   selection like the desktop's setpts + fps=, frame-exact trim, resize, H.264 / HEVC hardware,
   sound from `Audio`). Core done + verified (device tests, frame-by-frame PSNR check on the
   laptop). Export card (Lossless / Re-encode + options) checked on the phone. Reason it was moved up: the user saw stutter in the real-time parts of lossless
   exports (120 / 240 fps there – players can't decode that smoothly; Pixel HEVC is a single
   P-frame chain, so no frame can be dropped losslessly).
6. ✅ Smart export: every part whose playback rate differs from the output frame rate is
   re-encoded to it (source codec), the rest copied; one switch selects all, ticks per part.
   Join experiment passed on the Pixel (in-band parameter sets; the phone's decoder plays it).
7. ✅ Batch list, .cst load / save / share, export service with notification. Every export
   (single or batch) is an `ExportTask` (clip uri + treatment snapshot) run by `ExportManager`
   in the foreground `ExportService`; the batch list survives a restart (files/batch.json).
   .cst files are the desktop format (fingerprint check, both directions verified).
8. Signed release APK, icon, licence notices.
