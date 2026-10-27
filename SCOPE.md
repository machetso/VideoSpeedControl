# VideoSpeedControl – Scope

Desktop app (Windows + Linux) that gives full control over the speed of a video clip: a native
slow-motion clip (e.g. GoPro 240 fps) is split into sections, each with its own frame rate,
and exported losslessly (variable frame rate), with a smart re-encode, or fully re-encoded.
The first audio track is kept, stretched to the new length with its pitch
preserved (phone slow-mo sound restored to its real pitch); other tracks are discarded.
Stack: Python 3.12+, PySide6 (Qt 6), bundled FFmpeg/ffprobe (static GPL build).

## Processing modes

| Mode | When | Re-encode | Trim |
|---|---|---|---|
| **A – Lossless retime** (default) | speed = output fps ÷ source fps | no (stream copy, timestamps only) | keyframes only |
| Re-encode, every frame once | lossless speed, but resize/codec change | yes | frame-exact |
| **B – Frame selection** | faster than lossless speed | yes | frame-exact |
| **C – Interpolation** | slower than lossless speed | yes | frame-exact |

- Default = mode A, keeping the source codec. The UI shows the lossless speed for every output
  frame rate and lists why A is impossible as soon as a setting blocks it.
- Mode A trims only at keyframes. Reason shown in the UI: only keyframes are complete pictures;
  all other frames store differences to their neighbours and cannot be decoded once the preceding
  keyframe is cut away.

## Input
- Any FFmpeg-readable file, any resolution / frame rate / codec. Multiple files (dialog, drag & drop).
- Phone slow-mo (`com.android.capture.fps`): the capture rate counts as the original frame rate.
- Clip info: container, codec + profile, resolution, SAR/DAR, rotation, frame rate (nominal / average,
  CFR / VFR warning), frame count, duration, keyframe interval, pixel format, chroma, bit depth,
  colour space / transfer (SDR / HLG / PQ), bitrate, other streams.
- Multi-clip import shows a list with the codec info next to each file.

## Output
- Frame rates: 23.976, 24, 25, 29.97, 30, 50, 59.94, 60, 120, the source rate ("original"), custom;
  each entry shows "N× slower / faster" and the output length when every frame is kept.
- "Lossless only" switch: locks everything that needs re-encoding (mode A), only fps / container stay.
- Speed: free value + presets; shown as factor, percent and "× slower"; output duration live.
- Resolution presets (480p … DCI 4K, 9:16, 1:1) + custom + keep source.
- Aspect ratio: keep original (fit inside box) or manual ratio with fit mode pad / crop / stretch.
- Scaling methods with quality / speed description: nearest, bilinear, bicubic, area, spline, lanczos.
- Chroma subsampling selectable with tooltip: 4:4:4 high-end VFX, 4:2:2 broadcast TV,
  4:2:0 streaming (Netflix, YouTube). Bit depth 8 / 10-bit, default = source.
  Only combinations the chosen codec supports are offered.
- Interpolation: duplication, blending, FFmpeg minterpolate (CPU), RIFE (Vulkan GPU, also iGPU),
  RIFE high quality – each with quality and time estimate.
- Codecs:
  - lossless: FFV1, Ut Video (native FFmpeg encoder), MagicYUV, HuffYUV / FFVHuff, H.264 / HEVC /
    VP9 / AV1 lossless, AV2 lossless, QuickTime Animation, PNG / TIFF / DPX / EXR sequences.
    (Lagarith: FFmpeg can only decode it – not offered.)
  - lossy: H.264, HEVC, AV1 (SVT-AV1, libaom), VP9, ProRes (Proxy … 4444 XQ), DNxHR (LB … 444),
    CineForm, MJPEG, AV2 (AVM reference software – extremely slow, short clips only, no
    FFmpeg support yet); GPU encoders NVENC / Quick Sync / VAAPI / AMF where they really work.
- Must run on machines without a dedicated GPU (software encoders always available; hardware
  encoders are test-encoded at startup and only offered if they work).

## Timeline, trim, test encode
- Speed sections: mark frame ranges ([ / ]) that play at their own frame rate – slower or up to
  8× faster than the original; the rest stays real time. Without re-encoding → one variable-frame-rate file (sections start at any frame);
  with a codec → re-encoded to a chosen constant frame rate.
- Processing: Lossless / Smart re-encode / Re-encode – only the matching settings are enabled.
  Smart: sections marked "Re-encode" are encoded with the source codec at their own constant
  frame rate, everything else is copied, all joined into one file (H.264 / HEVC; joins only
  at safe keyframes, sections widened automatically; not playable on Apple devices).
- Play preview (Space): output timing at reduced size, no encoding; interpolation shown as blending.
- Simple timeline with thumbnails, playhead, keyframe markers, in/out points
  (mode A: snap to keyframes, B/C: frame-exact).
- Test encode of N frames (default 100) from the playhead with the exact output settings;
  side-by-side / wipe comparison; measured speed → reliable time estimate for clip and batch.

## Batch
- "Add to batch" in Preview & trim: snapshot of the clip (mode, settings, trim, sections) into a
  batch list; the same clip can be added several times (e.g. lossless + smart). "Clear
  sections"; undo / redo of every section edit (200 steps per clip).
- Batch list entries exported successfully are marked done and skipped by later exports
  (again after editing the entry or deleting its file).
- Double-click a batch entry: loads it into the editor – "Another encoding" (new entry) or
  "Edit this entry" (update it). Adding a clip that is already in the list asks first and
  offers name additions (checkboxes codec / preset / quality / resolution, name preview).
- Clip speed treatment files (.cst, JSON): sections + trim + output settings of one clip;
  bound to the video by content fingerprint – loads only onto that video (any file name).
- Individual settings per clip, "apply to all" button.
- Output folder, file name pattern, overwrite policy, queue with per-clip and overall progress,
  cancel.

## Milestones
1. Core: probe, frame map, lossless retime, re-encode, codecs, CLI, tests ✅
2. GUI basics: import, clip list, info panel, output settings ✅
3. Timeline + trimming ✅
4. Test encode, comparison view, time estimates ✅
5. Interpolation: RIFE integration ✅; 1:1 zoom in preview + comparison (zoom confirmed by user)
6. Batch queue ✅ (committed, awaiting user test); extensions after it: speed sections, smart
   re-encode, AV2, batch list, fast scrubbing (committed 2026-10-26, awaiting user test)
7. Packaging (PyInstaller) for Windows and Linux
