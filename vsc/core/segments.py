# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Speed sections: source frame ranges that play at their own frame rate.

Frames outside every section play in real time (the clip's real_fps). The result either keeps
every frame with its own duration (variable frame rate, stream copy – nothing is re-encoded,
so sections may start at any frame) or is re-encoded to one constant frame rate.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from fractions import Fraction


@dataclass(frozen=True)
class Segment:
    start: int          # first source frame
    end: int            # exclusive
    fps: Fraction       # each frame lasts 1/fps seconds
    reencode: bool = False              # smart re-encode: encode this section …
    out_fps: Fraction | None = None     # … at this constant frame rate
    smooth_start: bool = False          # speed ramp at the start border (see ramp_steps)
    smooth_end: bool = False            # … and at the end border


@dataclass(frozen=True)
class Piece:
    """A run of source frames [start, end) with one rate, starting at output time `t`."""
    start: int
    end: int
    rate: Fraction
    t: Fraction


def add(segments: list[Segment], new: Segment) -> list[Segment]:
    """Insert `new`; where it overlaps existing sections, the new one wins."""
    out = []
    for s in segments:
        if s.end <= new.start or s.start >= new.end:
            out.append(s)
            continue
        # the cut edges are new borders – no speed ramp there
        if s.start < new.start:
            out.append(replace(s, end=new.start, smooth_end=False))
        if s.end > new.end:
            out.append(replace(s, start=new.end, smooth_start=False))
    if new.end > new.start:
        out.append(new)
    return sorted(out, key=lambda s: s.start)


def pieces(segments: list[Segment], start: int, end: int, base: Fraction) -> list[Piece]:
    """Cover [start, end) with pieces: sections at their rate, the gaps at `base`."""
    runs = []
    pos = start
    for s in sorted(segments, key=lambda s: s.start):
        a, b = max(s.start, start), min(s.end, end)
        if a >= b:
            continue
        if a > pos:
            runs.append((pos, a, base))
        runs.append((a, b, Fraction(s.fps)))
        pos = b
    if pos < end:
        runs.append((pos, end, base))
    out, t = [], Fraction(0)
    for a, b, rate in runs:
        if out and out[-1].rate == rate:         # adjacent runs with the same rate
            prev = out.pop()
            out.append(Piece(prev.start, b, rate, prev.t))
        else:
            out.append(Piece(a, b, rate, t))
        t += Fraction(b - a) / rate
    return out


RAMP_SECONDS = Fraction(1, 2)    # output length of a speed ramp (user: 0.5 s, centred on the border)
RAMP_STEPS = 10                  # a ramp is played as this many steps, each with its own rate


def smooth_borders(segments: list[Segment]) -> set[int]:
    """Borders (frame positions) marked smooth by a section's smooth_start / smooth_end."""
    return ({s.start for s in segments if s.smooth_start}
            | {s.end for s in segments if s.smooth_end})


def ramp_steps(segments: list[Segment], start: int, end: int, base: Fraction,
               encode_at: Fraction | None = None) -> list[Segment]:
    """Speed ramps at the smooth borders of `segments` within [start, end) (gaps at `base`).

    The rate changes linearly in output time over RAMP_SECONDS, centred on the border, played as
    RAMP_STEPS sections. A side shorter than twice its share shortens the whole ramp. Exact
    fractions with half-even rounding – the Android app computes the same frames.
    `encode_at` (smart export): the steps are re-encoded at this rate.
    """
    smooth = smooth_borders(segments)
    if not smooth:
        return []
    ps = pieces(segments, start, end, base)
    steps = []
    n = Fraction(RAMP_STEPS)
    for left, right in zip(ps, ps[1:]):
        border = left.end
        if border not in smooth:
            continue
        ra, rb = left.rate, right.rate
        def before(t): return t * (3 * ra + rb) / 8      # source frames used before the border
        def after(t): return t * (ra + 3 * rb) / 8       # … and after it
        scale = min(Fraction(1), Fraction(left.end - left.start, 2) / before(RAMP_SECONDS),
                    Fraction(right.end - right.start, 2) / after(RAMP_SECONDS))
        t = RAMP_SECONDS * scale
        a, b = border - round(before(t)), border + round(after(t))
        if b <= a:
            continue
        mean = (ra + rb) / 2

        def pos(k: int) -> int:
            # frames played by the end of step k: integral of the linear rate, as a share of all
            x = Fraction(k) / n
            return a + round((x * ra + (rb - ra) * x * x / 2) / mean * (b - a))
        for k in range(RAMP_STEPS):
            p0, p1 = pos(k), pos(k + 1)
            if p1 > p0:
                rate = ra + (rb - ra) * (2 * k + 1) / (2 * n)
                steps.append(Segment(p0, p1, rate, encode_at is not None, encode_at))
    return steps


def all_smooth(segments: list[Segment]) -> list[Segment]:
    """Every border smooth (Easy mode: speed changes are always smoothed)."""
    return [replace(s, smooth_start=True, smooth_end=True) for s in segments]


def with_ramps(target: list[Segment], steps: list[Segment]) -> list[Segment]:
    """`target` with the ramp `steps` laid over it (steps win, like added sections)."""
    for s in steps:
        target = add(target, s)
    return target


def duration(ps: list[Piece]) -> Fraction:
    last = ps[-1]
    return last.t + Fraction(last.end - last.start) / last.rate if ps else Fraction(0)


def output_time(ps: list[Piece], frame: int) -> Fraction:
    """Output time at which source frame `frame` starts."""
    for p in ps:
        if frame < p.end:
            return p.t + Fraction(max(0, frame - p.start)) / p.rate
    return duration(ps)


def source_frame(ps: list[Piece], t: float) -> int:
    """Source frame shown at output time t."""
    i = max(0, bisect_right([float(p.t) for p in ps], t) - 1)
    p = ps[i]
    return min(p.end - 1, p.start + int((t - float(p.t)) * float(p.rate) + 1e-9))


def _num(v) -> str:
    return f"{float(v):.12g}"


def setpts_expr(ps: list[Piece]) -> str:
    """Output time in seconds of decoded frame N (N = 0 at ps[0].start) – for setpts."""
    first = ps[0].start
    expr = None
    for p in reversed(ps):
        term = f"{_num(p.t)}+(N-{p.start - first})/{_num(p.rate)}"
        expr = term if expr is None else f"if(lt(N,{p.end - first}),{term},{expr})"
    return expr


def setts_expr(ps: list[Piece], pts: list[int], time_base: Fraction, var: str,
               end_pts: int) -> str:
    """Packet timestamp expression for stream copy (setts bitstream filter).

    `var` is e.g. "PTS" or "DTS". Input ticks are taken relative to STARTPTS (the first copied
    packet = the start keyframe). Between section borders the mapping is linear, and every
    border lands exactly on its output time, so sections start precisely on time.
    """
    x0 = pts[ps[0].start]
    tick = 1 / time_base                           # output ticks per second (TB_OUT = TB)
    expr = None
    for i in reversed(range(len(ps))):
        p = ps[i]
        a = pts[p.start] - x0
        b = (pts[p.end] if p.end < len(pts) else end_pts) - x0
        out_len = Fraction(p.end - p.start) / p.rate          # seconds
        slope = out_len * tick / max(1, b - a)                 # output ticks per input tick
        term = f"{_num(p.t * tick)}+(({var}-STARTPTS)-{a})*{_num(slope)}"
        expr = term if expr is None else f"if(lt({var}-STARTPTS,{b}),{term},{expr})"
    return expr


# ------------------------------------------------------------------ editing (v0.92, like Android)

def quick_start(segments: list[Segment], last: int, trim_start: int = 0) -> int:
    """Start of a section ending at `last` when no start was marked: right after the section
    before it (sections follow each other seamlessly), the start of the section `last` lies in
    (that section is split), or the start of the trim range."""
    for s in segments:
        if s.start <= last < s.end:
            return s.start
    return max((s.end for s in segments if s.end <= last), default=trim_start)


def borders(segments: list[Segment], count: int) -> list[int]:
    """Positions where a section starts or ends inside the clip (draggable on the timeline)."""
    return sorted({b for s in segments for b in (s.start, s.end) if 0 < b < count})


def border_range(segments: list[Segment], border: int, count: int) -> tuple[int, int]:
    """How far the border at `border` may move: (lowest, highest) new position. A section
    keeps at least one frame; a border to real time may meet the next section."""
    ending = [s for s in segments if s.end == border]
    starting = [s for s in segments if s.start == border]
    lo = (max(s.start + 1 for s in ending) if ending
          else max((s.end for s in segments if s.end < border), default=0))
    hi = (min(s.end - 1 for s in starting) if starting
          else min((s.start for s in segments if s.start > border), default=count))
    return lo, hi


def moved_border(segments: list[Segment], border: int, to: int, count: int) -> list[Segment]:
    """The sections with the border at `border` moved to `to` (the neighbours follow)."""
    lo, hi = border_range(segments, border, count)
    q = max(lo, min(to, hi))
    out = []
    for s in segments:
        if s.end == border and s.start != border:
            s = replace(s, end=q)
        elif s.start == border:
            s = replace(s, start=q)
        out.append(s)
    return out


def with_smooth(segments: list[Segment], border: int, on: bool) -> list[Segment]:
    """Speed ramp on / off at `border` – on both sections sharing it."""
    return [replace(s, smooth_start=on) if s.start == border
            else replace(s, smooth_end=on) if s.end == border else s for s in segments]


def neighbour_rate(segments: list[Segment], index: int, at_start: bool, count: int,
                   real: Fraction) -> Fraction | None:
    """Rate on the other side of a border of section `index` (None = clip start / end)."""
    s = segments[index]
    border = s.start if at_start else s.end
    if border <= 0 or border >= count:
        return None
    other = next((x for x in segments if (x.end if at_start else x.start) == border), None)
    return other.fps if other else real
