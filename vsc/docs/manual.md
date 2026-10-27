# VideoSpeedControl user guide

VideoSpeedControl turns high-frame-rate footage – for example a GoPro at 240 fps or a phone's slow-motion recording – into slow motion, and can also speed parts of a clip up. Where possible it works **losslessly**: every original frame is kept and only its playing time changes, which takes seconds and costs no quality. When a change needs new pictures (another size, codec, or a speed that skips or adds frames), it re-encodes.

**Contents**

1. Quick start
2. The main window
3. Loading clips and clip information
4. Preview and trim
5. Output settings
6. Speed sections
7. Smart re-encode
8. Test encode and time estimates
9. Export and the batch list
10. AV2 (experimental)
11. Keyboard shortcuts
12. Tips and troubleshooting
13. Licence and credits

## 1. Quick start

1. Start VideoSpeedControl and drag one or more video files into the window (or click **Add files…**).
2. Choose the **Processing** mode in the *Output settings* on the right. **Lossless** is the default and the fastest.
3. Pick an output **Frame rate**. The drop-down shows how much slower (or faster) the clip plays and how long it becomes, e.g. *"25 fps (PAL) – 9.6× slower, 1:12 min"*.
4. Press **Space** in the *Preview & trim* tab to watch the result.
5. Open the **Export** tab, choose a folder and click **Start export**.

![The main window](images/overview.png)

### How slow motion works here

A 240 fps camera records 240 pictures per second. Played at 240 fps, that is real time. Played at 25 fps, the same 240 pictures take 9.6 seconds: the clip is **9.6× slower** – without a single new or missing picture. This is what *Lossless* does. Only when you want a speed that does not fit the frame rate (e.g. 20× slower at 25 fps) do pictures have to be skipped or calculated, which means re-encoding.

## 2. The main window

- **Clip list (top):** every loaded file with its device, codec, resolution, frame rate, length, the chosen output and an estimate of export time and size.
- **Tabs (bottom left):** *Preview & trim*, *Test encode*, *Clip info*, *Export*.
- **Output settings (bottom right):** everything about the output of the selected clip, with a summary at the bottom.
- **Help** (right end of the toolbar): this guide (**F1**), the guide as PDF, and *About*.

Each clip has its own settings. **Apply to all clips** copies the output settings of the selected clip to all others (trims and speed sections stay per clip).

## 3. Loading clips and clip information

Drag files or folders into the window, or use **Add files…**. Any format FFmpeg can read works. After loading, the app scans the clip (exact frame times and keyframes) and builds a small preview copy in the background (*"fast preview 45 %"* next to the frame number).

The **Clip info** tab lists everything about the file: container, codec and profile, resolution and aspect ratio, rotation, frame rate, number of frames, keyframe interval, pixel format, chroma subsampling, bit depth, colour space (SDR / HLG / PQ), bit rate, recording device and date, and audio.

![Clip info](images/clip_info.png)

### Phone slow motion

Phones such as the Google Pixel record slow motion at e.g. 240 fps but store it as a 30 fps file that already plays slowly. VideoSpeedControl reads the recording rate from the file and treats **240 fps as the original**: speeds and "× slower" always refer to real time. The clip list shows e.g. *"240 (slow-mo, file 29.97)"*.

## 4. Preview and trim

![Preview, speed sections and the summary](images/sections.png)

### Moving around

- Click or drag in the **timeline** (thumbnails with keyframe ticks below them), use the **frame number** box, or the buttons and keys: **←/→** one frame, **Shift+←/→** previous / next keyframe, **Home/End** first / last frame, mouse wheel.
- While you drag, the picture comes from the small preview copy – instantly. When the cursor rests for a moment, the sharp full-size frame replaces it.
- **Fit / 100 % / 200 %** zooms the picture; drag to pan, double-click to toggle.

### Play preview

**▶ Play preview** (or **Space**) plays the output at the chosen frame rate and speed – at reduced size and without encoding, so it starts at once. It plays from the cursor to the out-point. Motion interpolation and RIFE are shown as simple blending (they are too slow for real time). If the computer cannot decode fast enough (e.g. 240 fps real time), a note says that the preview runs slower than the export will.

### Trim (in / out)

**Set in (I)** and **Set out (O)** mark the first and last frame of the output; **Clear trim** removes them. The dimmed parts of the timeline are not exported.

In **Lossless** and **Smart re-encode** mode, in and out points **snap to keyframes**. A yellow hint explains why: only keyframes are complete pictures; all other frames store only the differences to their neighbours and cannot be shown once the keyframe before them is cut away. Choose *Re-encode* for frame-exact cuts.

## 5. Output settings

### Processing

| Mode | What happens | What you can change |
|---|---|---|
| **Lossless** | Every frame stays untouched; only its playing time changes. Seconds instead of minutes, no quality loss. | Frame rate, container, speed sections, trim (at keyframes) |
| **Smart re-encode** | Copies the clip and re-encodes only the sections you mark – see chapter 7. | Speed sections with their own output frame rate, quality and preset of the re-encoded parts, container |
| **Re-encode** | The whole clip is encoded again. | Everything: codec, size, speed, frame rate, interpolation |

Only the settings that the chosen mode can use are enabled.

![Output settings in Re-encode mode](images/settings_reencode.png)

### Frame rate and speed

- **Frame rate:** the standard rates (23.976 … 120 fps) plus the clip's own rate, marked *(original)*. Each entry shows the slow-down and the output length when every frame is kept.
- **Speed** (Re-encode): *Lossless* uses every frame once. *Custom* sets any speed (e.g. 0.05× = 20× slower) – faster than the lossless speed skips frames, slower calculates in-between frames (see *Interpolation*). *Presets…* offers common values.
- The line below shows the **output length** and how much slower or faster it is than the original.

### Codec and container

The codec list is grouped into **Lossless** (FFV1, Ut Video, MagicYUV, HuffYUV, H.264 / HEVC / VP9 / AV1 / AV2 lossless, QuickTime Animation, image sequences), **Lossy** (H.264, HEVC, AV1, VP9, ProRes, DNxHR, CineForm, MJPEG, AV2) and **Hardware** (NVIDIA, Intel, AMD – only offered if a test encode on your computer worked). Every entry has a tooltip explaining what it is good for. The **container** list only offers formats that can hold the chosen codec.

### Preset

How long the encoder searches for the best compression. At the same quality setting a slower preset gives a **smaller file** and takes **longer**; the visible quality hardly changes. Each entry says what it does, e.g. *"veryslow – slowest, smallest file"*. (For CineForm the row is called *Compression* – there it is a quality level.)

### Quality

Named levels that mean about the same for every codec; the codec's own number is shown in brackets:

| Level | Meaning |
|---|---|
| Visually lossless | No visible difference even in a still frame. Large files. |
| High (default) | Hardly any visible loss – good for further editing and archiving. |
| Good | Streaming quality (YouTube, Netflix): fine for watching. |
| Medium | Losses visible on a close look, e.g. in fine detail or dark areas. |
| Small file | Clearly visible losses – for previews or sending quickly. |

**Custom…** lets you enter the codec's own value. One level down makes the file roughly 30–50 % smaller.

### Chroma and bit depth

- **Chroma subsampling:** 4:4:4 (full colour detail – VFX, high-end), 4:2:2 (broadcast TV), 4:2:0 (streaming, Netflix, YouTube). Only combinations the codec supports are offered.
- **Bit depth:** 8-bit or 10-bit. *Like source* keeps what the clip has.

### Resolution, aspect and scaling

- **Resolution:** keep the source size, presets from 480p to DCI 4K (including 9:16 and 1:1) or custom.
- **Aspect:** keep the original proportions (fit inside the frame) or force a frame size / aspect ratio; **Fit** decides between black bars (pad), cutting off (crop) or stretching.
- **Scaling:** the resampling method with quality and speed ratings – Lanczos is the sharpest, Area the cleanest for strong downscaling.

### Interpolation

Used when the speed is slower than the lossless speed and new in-between pictures are needed:

- **Frame duplication** – repeats pictures; motion stutters. Fastest.
- **Frame blending** – cross-fades neighbours; smooth but with ghosting.
- **Motion interpolation (minterpolate)** – calculates real in-between pictures on the CPU; good for slow, even motion. Very slow.
- **RIFE (AI)** – neural network on the graphics card (Vulkan, also integrated graphics); clearly better motion. Works on 8-bit RGB. Not available together with speed sections or AV2.

### Sound

The **Sound** button right under *Processing* switches the sound on or off with one click: **🔊 Sound on – pitch preserved** (default) or **🔇 Sound off**. With sound on, the app takes the first audio track of the clip and stretches or compresses it to the new length of the video – the **pitch stays the same**, so there are no deep or squeaky voices. Speed sections get their own stretch factor each, so the sound follows every section. Very strong slow motion makes speech hard to understand (it is simply 10× slower), but it keeps its pitch.

**Phone slow motion:** phones store the sound of a slow-motion clip slowed down like a tape – it sounds deep. VideoSpeedControl first brings it back to its real pitch and real-time length, then stretches it to the video.

The sound is added after the video is finished, so a **lossless** video stays lossless; only the audio track is encoded (AAC in MP4 / MOV / MKV, Opus in WebM, PCM in AVI / MXF). Image sequences and AV2 files (FFmpeg cannot handle AV2 yet) stay without sound – the button is greyed out then, and its tooltip says why.

## 6. Speed sections

Speed sections give parts of a clip their own frame rate – for example the jump in slow motion, the run-up in real time, the landing 8× faster.

1. Move the cursor to the first frame and click **Section start [** (key **[**).
2. Move to the last frame and click **Section end ]** (key **]**). A dashed frame marks the range.
3. Choose the frame rate (from 23.976 fps up to **8× faster** than the original) and click **Add section**.

Sections appear as blue bands in the timeline and in the table below it, where you can change their frame rate, jump to them (click) or remove them (✕). Everything outside sections plays in **real time**. A new section that overlaps an existing one wins.

- **Magnetic cursor 🧲:** when you drag near a section, the cursor snaps to the frame right after it (to continue seamlessly) or – while you mark an end – to the frame right before the next section. Click 🧲 to switch it off.
- **Clear sections** (right) removes all sections after asking.
- **↶ Undo** (**Ctrl+Z**) and **↷ Redo** (**Ctrl+Shift+Z** or **Ctrl+Y**) step back and forward through every change to the sections – adding, changing, removing, clearing, loading – up to 200 steps, separately for each clip. Hover over the button to see which change it undoes.

### Saving and loading a treatment (.cst)

**Save treatment…** in the toolbar (**Ctrl+S**) saves the current clip's sections, trim and output settings as a *clip speed treatment* file (`.cst`, next to the clip by default). **Load treatment…** (**Ctrl+L**) – or dropping a `.cst` onto the window – loads it again.

A treatment belongs to exactly one video: it stores a fingerprint of the file's content and only loads onto that video. The file name does not matter – a renamed or moved copy still matches. If the video is not in the list yet but is still where it was when you saved, it is added automatically. A treatment never loads onto a different video, because its frame numbers would not fit.

How sections are exported depends on the processing mode:

- **Lossless:** every frame is kept with its own playing time – one file with a **variable frame rate**. Sections can start at any frame. Plays in all common players; editing programs prefer a constant frame rate. Very fast sections (e.g. 1920 fps) make players decode that many frames per second – choose re-encoding for smooth playback there.
- **Re-encode:** the whole clip is converted to the chosen **constant frame rate**; fast sections skip pictures, slow ones get in-between pictures.
- **Smart re-encode:** see the next chapter.

## 7. Smart re-encode

Smart re-encode combines both: sections marked **Re-encode** in the section table are encoded with the **source codec** at their own **Output fps**; everything else is copied unchanged. All parts are joined into **one file**.

![Output settings in Smart re-encode mode](images/settings_smart.png)

Things to know:

- **Only for H.264 and HEVC footage** (e.g. GoPro, phones). The codec is fixed to the source codec – otherwise the parts could not be joined.
- **Joins only at keyframes.** In / out points snap to them, and re-encoded sections are widened to the nearest keyframes automatically – the extra frames are re-encoded at the speed they have anyway. Some cameras write "open" keyframes where the following frames still depend on earlier ones; the app detects them when loading the clip and does not join there.
- **Not playable on Apple devices.** The joined file changes the decoder settings inside the stream (MP4 tag *hev1* / *avc3*). QuickTime, iPhone, iPad and Final Cut cannot play this – VLC, mpv, Windows, Android, Chrome and Firefox can. For Apple, re-encode the whole clip instead.
- The output frame rate you chose last becomes the default for the next re-encoded section.

## 8. Test encode and time estimates

The **Test encode** tab encodes a few frames (default 100) from the cursor position with the exact output settings. It shows the encoding speed, the file size and an **estimate for the whole clip**, and compares source and output **side by side** or with a **wipe** – zoomable to 100 % and 200 %. Test at a busy part of the clip for a safe estimate. The *FFmpeg command* button shows what is run.

![Test encode with side-by-side comparison](images/test_encode.png)

Estimates also appear in the clip list. Clips with the same settings share a test, scaled by their size.

## 9. Export and the batch list

![Export tab with the batch list](images/export.png)

- **Save to:** next to each source file, or a folder.
- **File name:** a pattern with placeholders – `{name}` source name, `{speed}` speed factor, `{slower}` how many times slower, `{fps}` output frame rate, `{codec}`, `{res}` output size, `{mode}` lossless / smart / reencode, `{n}` position in the queue.
- **If the file exists:** add a number, overwrite, or skip.
- **Export:** all clips, the selected clips, or the **batch list**.
- Progress is shown per clip and for the whole batch; **Cancel** stops it, and incomplete files are deleted.

### Batch list

**➕ Add to batch** (Preview & trim tab) saves the clip exactly as it is at that moment – processing mode, settings, trim and all sections – as an entry in the batch list. The sections stay in place, so you can add the same clip several times, e.g. once *Lossless* and once *Smart re-encode*. Later changes to the clip do not change entries already in the list. The list stays after the export; **Remove from list** and **Clear list** manage it. Entries that were exported successfully are marked **Done** and are not exported again when you click **Start export** later – only entries added (or failed / cancelled) since then run. To export a done entry again, change it with *Edit this entry*, or delete its output file. Use `{mode}` in the file name to tell the versions apart.

**Double-click an entry** in the batch list to open it again: its sections, trim and settings are loaded into Preview & trim (the clip's previous sections can be brought back with ↶ Undo). You are asked what you want to do:

- **Another encoding** – change codec, preset, quality or size and click **➕ Add to batch**: a new entry is added, the old one stays.
- **Edit this entry** – change it and click **✔ Update batch entry**: the entry is replaced.

Whenever you add a clip that is already in the batch list, VideoSpeedControl asks whether you want another encoding and offers **name additions** with checkboxes – codec, preset, quality and resolution, e.g. `jump_x265_slow_high_1920x1080.mp4`. A preview shows the resulting file name; your choice of boxes is remembered.

## 10. AV2 (experimental)

AV2 is the successor of AV1 (AOMedia, specification 1.0 from May 2026), about 30 % smaller at the same quality. FFmpeg cannot handle AV2 yet, so the app uses the AVM reference software. It is a research tool and **extremely slow** – about 75 seconds per 1080p frame on a laptop CPU, about 20 seconds at 360p – so use it for short clips and small sizes. Test encodes use at most 5 frames. Output is IVF or WebM; hardly any player can play AV2 yet. On Linux the encoder is built with `tools/fetch_avm.py`; without it, AV2 is shown as unavailable.

## 11. Keyboard shortcuts

| Key | Action |
|---|---|
| F1 | This user guide |
| Ctrl+O | Add files |
| Delete | Remove the selected clips |
| Space | Play / stop the preview |
| ← / → | Previous / next frame |
| Shift+← / → | Previous / next keyframe |
| Home / End | First / last frame |
| I / O | Set in / out point |
| [ / ] | Section start / end |
| Ctrl+Z | Undo the last change to the sections |
| Ctrl+Shift+Z / Ctrl+Y | Redo |
| Ctrl+S | Save treatment (.cst) |
| Ctrl+L | Load treatment (.cst) |

## 12. Tips and troubleshooting

- **Which mode?** Lossless whenever the frame rates fit – it is instant and perfect. Smart re-encode when only some parts need a constant frame rate. Re-encode for a different size, codec, or editing-friendly constant frame rate.
- **Editing programs and variable frame rate:** DaVinci Resolve and Premiere handle variable-frame-rate files poorly. Export with Re-encode (e.g. ProRes or DNxHR) for editing.
- **The preview stutters:** very high frame rates (240 fps real time) need more decoding power than many laptops have – the export is not affected.
- **No hardware encoder:** hardware encoders are only offered when a test encode on your computer works; software encoders always work.
- **RIFE is slow or unavailable:** RIFE needs a Vulkan-capable graphics card; on integrated graphics it is slow, without Vulkan it is not offered.
- **The sound is hard to understand:** that is normal for strong slow motion – 10× slower speech keeps its pitch but is stretched. Switch the sound off (🔇) or add music later.
- **Smart re-encode is greyed out:** the clip is not H.264 / HEVC, the keyframe analysis is still running, or no keyframe allows a join.

## 13. Licence and credits

Copyright © 2026 Alex Vulcu. Concept, architecture, direction, and curation by Alex Vulcu. Implementation assisted by generative AI tools. Licensed under the MIT License – see the LICENSE file.

VideoSpeedControl uses other open-source software with its own licence: **FFmpeg** (GPL build, includes x264 / x265 and the Rubber Band time-stretching library), **Qt / PySide6** (LGPL), **rife-ncnn-vulkan** with the RIFE model (MIT) and **AVM**, the AV2 reference software (BSD-3-Clause-Clear). Details are in THIRD_PARTY_NOTICES.md.
