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
        if s.start < new.start:
            out.append(replace(s, end=new.start))
        if s.end > new.end:
            out.append(replace(s, start=new.end))
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
