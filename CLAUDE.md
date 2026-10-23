# VideoSpeedControl – developer notes

Read SCOPE.md for the agreed feature set and milestone status.

## Setup
- venv: `.venv/` (created with `--without-pip` + get-pip.py, because python3-venv/ensurepip is
  not installed system-wide). Run things with `.venv/bin/python`.
- FFmpeg: `python tools/fetch_ffmpeg.py [linux|windows]` → `vendor/ffmpeg/<platform>-x64/`.
  `vsc/core/ffmpeg_bin.py` prefers the bundled copy, then `VSC_FFMPEG_DIR`, then PATH.
- Tests: `.venv/bin/python -m pytest tests -q` (test clips are generated into tests/media).
- CLI: `.venv/bin/python -m vsc info CLIP`, `... encode CLIP -o DIR --fps 25 [--codec x264 ...]`.

## Layout
- `vsc/core/` – no Qt imports; GUI-independent and testable.
  - `probe.py` – MediaInfo (ffprobe) and FrameMap (packet scan: exact pts, keyframes)
  - `formats.py` – catalogue: fps, resolutions, chroma, scalers, interpolation, codecs + UI texts
  - `encoders.py` – encoder detection, pix_fmt lists, hardware test encodes (cached in
    ~/.config/VideoSpeedControl/encoders.json per FFmpeg version)
  - `job.py` – OutputSettings (per clip), Trim, Job (mode decision, sizes, formats)
  - `command.py` – Job → ffmpeg args; `runner.py` – execution, progress, cancel
- `vsc/gui/` – PySide6 (milestone 2+).

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
