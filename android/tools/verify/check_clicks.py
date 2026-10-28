#!/usr/bin/env python3
# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Sound sync of an export of synth_clicks240.mp4 (a click every 0.5 s at 240 fps).

Usage: check_clicks.py FFMPEG OUTPUT.mp4 SLOWER_A SLOWER_B SLOWER_C
Sections (as in AudioSyncDeviceTest / the desktop test): frames 100–340, 400–560, 700–760,
each SLOWER_x times slower than real time; the rest real time. Prints, for every click, how far
its onset (first sample above half the local peak) is from the time its frame is shown.
"""
import array
import subprocess
import sys
from fractions import Fraction as F


def pieces(segs, start, end, base):
    runs, pos = [], start
    for a, b, r in segs:
        if a > pos:
            runs.append((pos, a, base))
        runs.append((a, b, r))
        pos = b
    if pos < end:
        runs.append((pos, end, base))
    out, t = [], F(0)
    for a, b, r in runs:
        out.append((a, b, r, t))
        t += F(b - a) / r
    return out


def output_time(ps, frame):
    for a, b, r, t in ps:
        if frame < b:
            return t + F(max(0, frame - a)) / r
    a, b, r, t = ps[-1]
    return t + F(b - a) / r


def main():
    ff, path, *slower = sys.argv[1:]
    sa, sb, sc = (int(x) for x in slower)
    segs = [(100, 340, F(240, sa)), (400, 560, F(240, sb)), (700, 760, F(240, sc))]
    ps = pieces(segs, 0, 960, F(240))
    pcm = subprocess.run([ff, "-v", "error", "-i", path, "-map", "0:a", "-ac", "1", "-ar", "48000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    s = array.array("h", pcm)
    worst_rt, worst_st = 0.0, (0.0, 0.0)
    for f in range(120, 960, 120):
        want = float(output_time(ps, f))
        lo, hi = max(0, int((want - 0.4) * 48000)), min(len(s), int((want + 0.4) * 48000))
        peak = max(range(lo, hi), key=lambda k: abs(s[k]))
        onset = next(k for k in range(lo, peak + 1) if abs(s[k]) > abs(s[peak]) // 2)
        err = onset / 48000 - want
        rate = next(r for a, b, r, _ in ps if a <= f < b)
        slow = float(240 / rate)
        kind = "real time" if slow == 1 else f"{slow:g}× slower"
        print(f"  frame {f:3d} ({kind:12s}): want {want:7.3f} s, onset {err * 1000:+7.1f} ms, "
              f"spread {(peak - onset) / 48000 * 1000:5.1f} ms")
        if slow == 1:
            worst_rt = max(worst_rt, abs(err))
        else:
            worst_st = (min(worst_st[0], err), max(worst_st[1], err))
    dur = len(s) / 48000
    print(f"  sound {dur:.3f} s (video {float(output_time(ps, 960)):.3f} s); real-time parts "
          f"within ±{worst_rt * 1000:.1f} ms, stretched {worst_st[0] * 1000:+.1f} … "
          f"{worst_st[1] * 1000:+.1f} ms")


if __name__ == "__main__":
    main()
