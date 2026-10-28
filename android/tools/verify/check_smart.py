#!/usr/bin/env python3
# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Check a smart export from the phone: decodes cleanly, copied frames bit-identical, timing.

Usage: check_smart.py FFMPEG_DIR SOURCE.mp4 OUTPUT.mp4 PARTS
PARTS as logged by SmartDeviceTest, e.g. "C0-48:48,E48-144:56,C144-576:432" (C = copied,
E = encoded; source frames start-end : output frames).
"""
import subprocess
import sys
from pathlib import Path


def hashes(ffmpeg: str, path: str) -> list[str]:
    out = subprocess.run([ffmpeg, "-v", "error", "-noautorotate", "-i", path, "-map", "0:v:0",
                          "-fps_mode", "passthrough", "-f", "framemd5", "-"],
                         capture_output=True, text=True, check=True).stdout
    return [ln.rsplit(",", 1)[1].strip() for ln in out.splitlines() if not ln.startswith("#")]


def main() -> None:
    ffdir, src, out, spec = sys.argv[1:5]
    ffmpeg, ffprobe = str(Path(ffdir) / "ffmpeg"), str(Path(ffdir) / "ffprobe")
    parts = []
    for p in spec.split(","):
        kind, rest = p[0], p[1:]
        rng, frames = rest.split(":")
        a, b = (int(x) for x in rng.split("-"))
        parts.append((kind, a, b, int(frames)))

    dec = subprocess.run([ffmpeg, "-v", "error", "-i", out, "-f", "null", "-"], capture_output=True, text=True)
    errors = [ln for ln in dec.stderr.splitlines() if ln.strip()]
    print(f"decode: {'clean' if dec.returncode == 0 and not errors else f'{len(errors)} error lines'}")
    for ln in errors[:5]:
        print("   ", ln)

    tag = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v", "-show_entries",
                          "stream=codec_tag_string,width,height", "-of", "csv=p=0", out],
                         capture_output=True, text=True).stdout.strip()
    print(f"stream: {tag}")
    s, o = hashes(ffmpeg, src), hashes(ffmpeg, out)
    print(f"frames: output {len(o)}, planned {sum(p[3] for p in parts)}")
    pos = 0
    for kind, a, b, n in parts:
        if kind == "C":
            same = o[pos:pos + n] == s[a:b]
            print(f"  copied  {a:4d}-{b:4d}: {n:4d} frames, bit-identical: {same}")
        else:
            print(f"  encoded {a:4d}-{b:4d}: {n:4d} frames")
        pos += n
    pts = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", out], capture_output=True, text=True).stdout.split()
    t = sorted(float(x) for x in pts)
    d = [b - a for a, b in zip(t, t[1:])]
    print(f"timing: {t[0]:.4f} … {t[-1]:.4f} s, frame step {min(d) * 1000:.2f}–{max(d) * 1000:.2f} ms, "
          f"monotonic: {all(x > 0 for x in d)}")


if __name__ == "__main__":
    main()
