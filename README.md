# VideoSpeedControl

![VideoSpeedControl](vsc/gui/resources/icon_256.png)

Turn high-frame-rate footage (e.g. GoPro 240 fps, phone slow motion) into slow-motion video –
losslessly by retiming when possible, otherwise by re-encoding with frame selection or
interpolation. Speed sections (slower and faster parts in one clip), smart re-encode (only
the marked parts are re-encoded), batch export, a test encode with comparison and time
estimates, AV2 (experimental). Windows and Linux.

- **User guide:** [vsc/docs/manual.md](vsc/docs/manual.md) – also in the app (Help → User
  guide, F1) and as [PDF](vsc/docs/VideoSpeedControl_Manual.pdf)
- Feature set and milestones: [SCOPE.md](SCOPE.md)

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/python tools/fetch_ffmpeg.py          # downloads the bundled FFmpeg
.venv/bin/python tools/fetch_rife.py            # RIFE AI interpolation (Vulkan GPU, ~430 MB download)
.venv/bin/python tools/fetch_avm.py             # optional: AV2 (builds AVM, needs cmake + nasm)
```

Artwork and documentation:

```bash
.venv/bin/python tools/make_icons.py            # icons + start screen from assets/*.webp
.venv/bin/python tools/build_docs.py [--screenshots]   # PDF user guide (and new screenshots)
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
.venv/bin/python -m vsc encode clip.mp4 -o out --fps 25 --speed 0.05 --codec x264 --interp rife
.venv/bin/python -m vsc encode clip.mp4 -o out --codec prores --profile hq --size 1920x1080
.venv/bin/python -m vsc encoders
```

## Packaging

```bash
.venv/bin/pip install pyinstaller
.venv/bin/python -m PyInstaller packaging/VideoSpeedControl.spec --noconfirm   # → dist/VideoSpeedControl/
```

The bundle contains FFmpeg, RIFE and (if built) AVM from `vendor/`. Windows installers are built
by GitHub Actions (`.github/workflows/windows.yml`). Pushing a tag `vX.Y.Z` that matches
`vsc/__init__.py` creates a release with `VideoSpeedControl-X.Y.Z-setup.exe`. A test build can
be started by hand under Actions → "Windows build" → Run workflow.

## License & Attribution

- **Concept, Architecture & Design:** Alex Vulcu
- **Implementation:** Developed and curated by Alex Vulcu with AI-assisted code generation.
- **License:** Distributed under the [MIT License](LICENSE).

The bundled tools keep their own licences – FFmpeg (GPL v3 build), Qt / PySide6 (LGPL v3),
rife-ncnn-vulkan (MIT), AVM (BSD-3-Clause-Clear). See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), including what distributing a package with
them requires.
