# Third-party software

VideoSpeedControl itself is licensed under the [MIT License](LICENSE). It uses the following
programs and libraries, which keep their own licences. FFmpeg, rife-ncnn-vulkan and AVM are
separate programs that VideoSpeedControl starts as external processes; they are not linked
into it.

| Component | Used for | Licence | Source |
|---|---|---|---|
| **FFmpeg / FFprobe** (static "gpl" build by BtbN, incl. x264, x265, SVT-AV1, libaom, libvpx, Rubber Band …) | decoding, encoding, filtering, sound time-stretching, analysis | **GNU GPL version 3** (`--enable-gpl --enable-version3`) – licence text in `vendor/ffmpeg/<platform>/LICENSE.txt` | https://ffmpeg.org, https://github.com/BtbN/FFmpeg-Builds |
| **Qt 6 / PySide6** (6.12) | user interface | GNU LGPL version 3 | https://www.qt.io, https://doc.qt.io/qtforpython/ |
| **rife-ncnn-vulkan** (20221029) with the RIFE v4.6 model | AI frame interpolation | MIT – `vendor/rife/<platform>/LICENSE` | https://github.com/nihui/rife-ncnn-vulkan, https://github.com/hzwer/Practical-RIFE |
| **AVM** (AV2 reference software, v1.0.0) | AV2 encoding / decoding | BSD-3-Clause-Clear plus the Alliance for Open Media patent licence – `vendor/avm/<platform>/LICENSE`, `PATENTS` | https://github.com/AOMediaCodec/avm |

## Notes for anyone distributing VideoSpeedControl with these programs

- The source repository does **not** contain these binaries (`vendor/` is not committed); the
  scripts in `tools/` download or build them.
- A package that **includes** the FFmpeg binaries must meet the GPL v3: include its licence
  text and offer the corresponding FFmpeg source code (the exact build version), e.g. by
  linking the BtbN release and the FFmpeg source tag it was built from.
- A package that includes PySide6 / Qt must allow users to replace the Qt libraries (LGPL v3)
  and include the LGPL licence text.
- Keep the LICENSE / PATENTS files of rife-ncnn-vulkan and AVM next to their programs.
