# VideoSpeedControl

Turn high-frame-rate footage (e.g. GoPro 240 fps) into slow-motion video – losslessly by
retiming when possible, otherwise by re-encoding with frame selection or interpolation.
Windows and Linux. See [SCOPE.md](SCOPE.md).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/python tools/fetch_ffmpeg.py          # downloads the bundled FFmpeg
```

## GUI

```bash
.venv/bin/python -m vsc.gui [clip.mp4 ...]       # or drag & drop files into the window
```

## Command line (core, for testing)

```bash
.venv/bin/python -m vsc info clip.mp4
.venv/bin/python -m vsc encode clip.mp4 -o out --fps 25                    # lossless retime
.venv/bin/python -m vsc encode clip.mp4 -o out --fps 50 --start 100 --end 900   # trimmed (keyframes)
.venv/bin/python -m vsc encode clip.mp4 -o out --fps 25 --speed 0.05 --codec x264 --interp mci
.venv/bin/python -m vsc encode clip.mp4 -o out --codec prores --profile hq --size 1920x1080
.venv/bin/python -m vsc encoders
```

## Licence note

The bundled FFmpeg build is GPL (contains x264 / x265). Fine for private use; distributing the
app requires GPL compliance.
