# VideoSpeedControl for Android – user guide

VideoSpeedControl lets you decide which parts of a video play in slow motion, at normal speed or faster. It is made for slow-motion recordings – for example a phone's 240 fps slow motion – but works with any video. You mark **Clip Sections**, give each one its own speed, and save the result as a new video. The original is never changed.

This guide explains everything briefly and the **Pro** mode in detail.

**Contents**

1. Easy and Pro
2. Quick start
3. The screen
4. Frames, frame rates and speed
5. Moving precisely
6. Clip Sections in Pro
7. Trim
8. Export: lossless, smart, re-encode
9. Sound
10. Batch list
11. Clip Speed Treatments
12. The menu behind the logo
13. Tips and troubleshooting
14. Licence and third-party notices

## 1. Easy and Pro

The app has two modes. Switch at any time – tap the **Easy / Pro** badge next to the app name, use the switch in the save card, or choose in the menu behind the logo. Your sections and settings are kept.

- **Easy** (the default) shows only what you need for quick results: Clip Sections with a simple video speed ("4× slower"), the yellow brackets on the timeline to cut, and **Save video**. Every speed change is smoothed automatically. Smart export keeps the source codec, re-encode uses a codec chosen by the app in high quality.
- **Pro** adds everything for exact work: frame numbers and frame rates, keyframe buttons, section start / end at the playhead, smooth transitions chosen per border, the trim card, a choice of which parts smart export re-encodes, codec, quality and resolution for re-encoding, a speed for re-encoding without sections, and saving changes back into a batch entry.

## 2. Quick start

1. Tap **Choose clip** and pick a video – ideally a slow-motion recording. The app's gallery shows the camera folder, newest first; **Other files…** opens any other file.
2. Move the playhead to where a section should end and tap **End ]**. The first section starts at the beginning of the clip, each further one right after the one before.
3. Tap the section in the list (or on the timeline) and choose its speed.
4. Drag the yellow brackets on the timeline to cut away the start and end.
5. Tap **▶ Play preview** to check, then **Save video**. The video appears in *Movies/VideoSpeedControl*.

## 3. The screen

From top to bottom:

- **Top bar** – the logo (opens the menu), the **Easy / Pro** badge and **＋ Clip** for the next video. If the current clip has unsaved sections, the app asks whether to add it to the batch list first.
- **Preview** – the current frame. Drag sideways on the picture to move frame by frame.
- **Timeline** – pictures of the clip with the Clip Sections (coloured, labelled with their speed), their borders, the smooth transitions, the yellow trim brackets, the keyframe ticks below the strip and the playhead.
- **Transport** – play preview, the output length and speed, the magnet 🧲 and the buttons to move through the clip.
- **Clip Sections** – the section list and the section editor.
- **Trim** (Pro) – in and out points as frame numbers.
- **Save / Export** – mode, frame rate, codec and the save buttons.
- **Batch list** – videos waiting to be saved, or already saved.
- **Clip Speed Treatment** – save and load your edit as a file.
- **Clip info** – recording details: device, date, size, codec, frame rate, slow-motion factor, sound.

## 4. Frames, frame rates and speed

A video is a series of still pictures, the **frames**. Pro shows frame numbers and frame rates, so it helps to know how they relate:

- The **recording rate** (shown as *original*) is how many frames per second the camera recorded – 240 fps for a phone's 240 fps slow motion. Phones store such clips to play at about 30 fps; the app reads the real rate from the file.
- A section's **frame rate** says how many of these frames play per second. At the recording rate the section plays in **real time**; at 30 fps a 240 fps recording plays **8× slower**; above the recording rate it plays **faster**.
- The **output frame rate** is the frame rate of the saved video (24 to 120 fps). It matters for smart export and re-encoding – see section 8.

Pro lists the frame rates with the speed next to them; *(original)* marks the recording rate, which plays in real time. Easy shows only the speed ("4× slower", "real time"); there *(original)* marks the speed at which every recorded frame is shown once at the output frame rate – the phone's own slow motion.

## 5. Moving precisely

Pro shows a line above the transport buttons: *Frame 812 / 2400 · keyframe · source 3.38 s · output 9.20 s*. *Source* is the time in the original recording, *output* the time in the saved video (or *cut* when the frame is outside the trim).

The buttons, from left to right:

- **|◀** first frame, **▶|** last frame
- **− 🔑 / 🔑 +** previous / next **keyframe** (Pro) – see section 7 for why keyframes matter
- **◀ 1 / 1 ▶** one frame back / ahead

On the timeline, **tap** to move the playhead (and select the section there) and **drag** to scrub. Dragging on the preview picture moves frame by frame, more finely than the timeline.

The **magnet 🧲** makes the playhead snap to section borders when it comes close – useful to start the next section exactly where the previous one ends. Tap it to switch it on or off.

While the app prepares the pictures for scrubbing, a thin bar on the timeline shows the progress. Clips you open again are ready almost at once – the app keeps these previews for a while (see section 12).

## 6. Clip Sections in Pro

**New sections play at** sets the frame rate of the next section you add.

**Adding a section.** Move to the last frame of the section and tap **End ]**. Without a marked start the section starts right after the section before it – the first one at the start of the clip. So for the next section just move on and tap **End ]** again. Tap **[ Start** first only when a section should begin somewhere else; **Cancel** drops a marked start. Inside an existing section, **End ]** splits it. Frames between sections play in real time.

**Editing a section.** Tap it in the list or on the timeline. The section editor shows:

- **Frame rate** – its speed.
- **Start = playhead / End = playhead** – move a border to the current frame.
- **Smooth transition in / out** – instead of jumping, the speed changes evenly over 0.5 s, centred on the border (in Easy every speed change is smooth). The switch is off when the speed on the other side is the same.
- **Remove section**, and **Done** to close the editor.

You can also **drag a border** on the timeline (it has a small grip); the preview follows it.

**Undo / Redo** keep up to 200 steps per clip; the buttons show how many there are, and Pro shows the **last change**. **Clear sections** removes all sections after asking – this can be undone too.

## 7. Trim

In Easy you cut with the yellow brackets on the timeline. Pro also has the **Trim** card: **Set in** and **Set out** at the playhead, **Reset** for the whole clip, and the range as frame numbers.

Lossless and smart export can only cut at **keyframes** (the ticks under the timeline). Only keyframes are complete pictures; all other frames store differences to their neighbours. In these modes in and out snap to the nearest keyframe. Re-encoding cuts at any frame.

## 8. Export: lossless, smart, re-encode

Choose the mode at the top of the export card.

**Lossless** keeps every frame unchanged and only changes when it is shown. It is very fast and has no quality loss. Without sections, Pro lets you choose the **frame rate** – each choice shows the resulting speed and length. With sections, the sections set the timing and the rest plays in real time. The saved video keeps the different frame rates of its parts; fast parts of a slow-motion clip keep their high frame rate, which many players can't show smoothly, and some devices don't play such files at all.

**Smart** re-encodes only the parts that need it and copies the rest unchanged – much faster than re-encoding everything, and the copied parts keep their full quality. Pro shows:

- **Output frame rate** of the saved video.
- **Re-encode everything that does not play at N fps** – the automatic choice. Every part whose frame rate differs from the output frame rate is re-encoded to it, the others are copied.
- The **list of parts** with a tick for each – switch the automatic choice off to decide yourself. A copied part keeps its own frame rate ("may not play smoothly").
- **Quality of re-encoded parts**.
- A summary: how many parts and frames are re-encoded and the output length. Re-encoded parts are widened to the nearest keyframes.

Smart works with H.264 and HEVC videos, not with HDR (10-bit) videos yet. The re-encoded parts always use the codec and size of the source – otherwise the parts could not be joined. The result may not play on Apple devices.

**Re-encode** makes a completely new video at a constant frame rate: slow parts repeat frames, fast parts drop them, and it plays smoothly everywhere. It uses the phone's hardware encoder and cuts at any frame. Pro offers:

- **Output frame rate**.
- **Speed** (only without sections): *Every frame once* plays each recorded frame once at the output frame rate; the other choices set the speed directly – slower than *every frame once* repeats frames.
- **Codec**: **AV1 (fast)** – small files, needs a hardware AV1 encoder (only offered when the phone has one); **AV1 (best quality, slow)** – the software encoder, much slower; **HEVC (H.265)** and **H.264** – play almost everywhere, H.264 even on old devices.
- **Quality**: Good, High or Very high.
- **Resolution**: no change, or a smaller size (2160p down to 480p).
- A line with size, frames, length and the approximate bit rate.

If the phone has no encoder for the chosen codec, size and frame rate, a red note says so before you save. Choose another codec, a lower resolution or a lower frame rate.

**Saving.** **Export** (Easy: *Save video*) saves the video to *Movies/VideoSpeedControl*. The file appears only when it is complete; until then the card shows *Still saving … n %*. The app keeps working in the background – you can switch to other apps. When it is done, **▶ Play** and **📁 Open folder** appear.

## 9. Sound

The **Sound** switch adds the sound to the saved video. It is stretched to the new length of every part and keeps its natural pitch – slow motion doesn't sound deeper. Phones store the sound of slow-motion clips slowed down like a tape; the app restores the real pitch first.

## 10. Batch list

Collect several videos – or several versions of the same video – and save them in one go.

- **Add to batch** (Easy: *Add as new version*) adds the current clip with all its settings.
- **Export batch (n)** saves all entries that are not saved yet; saved entries are skipped. **Cancel all** stops it.
- Each entry shows a picture and its mode. **ⓘ** shows the file name, the settings and the result; the green ▶ plays the saved video (grey when the file has been deleted since).
- **Tap an entry** to load it into the editor. Change it and tap **✔ Save changes to this entry** (Pro) – or add it as another version.
- **Remove done** clears the saved entries; **✕** removes one.

## 11. Clip Speed Treatments

A **Clip Speed Treatment** (.cst file) stores everything you planned for a clip – sections, trim, speeds and export settings – so you can change it again later.

- **Save** puts it into *Documents/VideoSpeedControl/Clip Speed Treatments*.
- **Load** opens a treatment and applies it. It only loads onto the video it was made for – the app recognises the video by its content, so a renamed or moved file still matches.
- **Share** sends it, for example to your computer.

The file format is the same as in the desktop app for Linux and Windows: you can start on the phone and continue on the computer, or the other way round.

## 12. The menu behind the logo

Tap the logo at the top left.

- **Mode** – Easy or Pro, with what each one offers.
- **Language** – the app follows the phone's language; choose another here (English, German, Spanish, French, Romanian, Hebrew, Klingon).
- **Folders** – where the saved videos and the Clip Speed Treatments are, each with **Open**.
- **Previews** – the space the stored previews take and **Delete previews**. The app stores the pictures it prepares for scrubbing, so a clip opened again is ready at once. Previews nobody needs are deleted automatically 2 minutes after the start, when the app is idle; together they take at most 2 GB.
- **← Back** or **Close & return to app** go back to the editor.

## 13. Tips and troubleshooting

- **The saved video stutters on some players.** Lossless videos and copied smart parts keep their recorded frame rate. Use smart export with the automatic choice, or re-encode.
- **The video doesn't play on an iPhone or Mac.** Smart exports may not play on Apple devices. Re-encode with HEVC or H.264.
- **In and out jump when I set them.** In lossless and smart mode they snap to keyframes (section 7). Re-encode cuts at any frame.
- **"Analysing the keyframes of this clip …"** – smart export first looks for the frames where parts can be joined. This takes a moment after opening a clip.
- **A red note says the phone has no encoder.** Every phone has different video encoders. Choose another codec, resolution or frame rate – or smart instead of re-encode, or the other way round.
- **Saving takes long.** Re-encoding works through every frame; AV1 (best quality) is much slower than the other codecs. Lossless is the fastest.
- **A batch entry fails after the app was closed.** Clips opened through *Open with* or *Share* from another app may only be readable while the app is running. Open them in VideoSpeedControl's own gallery instead.

## 14. Licence and third-party notices

Copyright © 2026 Alex Vulcu. Concept, architecture, direction, and curation by Alex Vulcu. Implementation assisted by generative AI tools.

VideoSpeedControl is licensed under the **MIT License**:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The Android app uses the following open-source software. All of it is licensed under the **Apache License, Version 2.0** (https://www.apache.org/licenses/LICENSE-2.0):

| Software | Used for |
|---|---|
| AndroidX Media3 (ExoPlayer, Transformer, Effect, Common, UI Compose) – including **Sonic** (Android Open Source Project, based on Sonic by Bill Cox) | preview playback, video helpers, stretching the sound with the pitch kept |
| Jetpack Compose (UI, Material 3) | the user interface |
| AndroidX Core, Activity, Lifecycle | app basics |
| Kotlin standard library and kotlinx.coroutines (JetBrains) | the programming language and background work |

Copyright of these components belongs to The Android Open Source Project, Google LLC and JetBrains s.r.o. and their contributors. They are distributed on an "AS IS" basis, without warranties or conditions of any kind.

Video encoding and decoding use the codecs built into Android; no further codec software is included.
