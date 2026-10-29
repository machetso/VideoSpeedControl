package com.alexvulcu.videospeedcontrol.core

/**
 * Speed sections: source frame ranges that play at their own frame rate.
 * Port of `vsc/core/segments.py` – same semantics, so .cst files mean the same on both platforms.
 *
 * Frames outside every section play in real time (the clip's real fps). The result either keeps
 * every frame with its own duration (variable frame rate, nothing re-encoded) or is re-encoded to
 * one constant frame rate.
 */
data class Segment(
    val start: Int,                 // first source frame
    val end: Int,                   // exclusive
    val fps: Rational,              // each frame lasts 1/fps seconds
    val reencode: Boolean = false,  // smart re-encode: encode this section …
    val outFps: Rational? = null,   // … at this constant frame rate
    val smoothStart: Boolean = false, // speed ramp at the start border (see Segments.rampSteps)
    val smoothEnd: Boolean = false,   // … and at the end border
)

/** A run of source frames [start, end) with one rate, starting at output time [t] (seconds). */
data class Piece(val start: Int, val end: Int, val rate: Rational, val t: Rational)

object Segments {

    /** Insert [new]; where it overlaps existing sections, the new one wins. */
    fun add(segments: List<Segment>, new: Segment): List<Segment> {
        val out = mutableListOf<Segment>()
        for (s in segments) {
            if (s.end <= new.start || s.start >= new.end) {
                out += s
                continue
            }
            // the cut edges are new borders – no speed ramp there
            if (s.start < new.start) out += s.copy(end = new.start, smoothEnd = false)
            if (s.end > new.end) out += s.copy(start = new.end, smoothStart = false)
        }
        if (new.end > new.start) out += new
        return out.sortedBy { it.start }
    }

    /** Cover [start, end) with pieces: sections at their rate, the gaps at [base]. */
    fun pieces(segments: List<Segment>, start: Int, end: Int, base: Rational): List<Piece> {
        data class Run(val a: Int, val b: Int, val rate: Rational)
        val runs = mutableListOf<Run>()
        var pos = start
        for (s in segments.sortedBy { it.start }) {
            val a = maxOf(s.start, start)
            val b = minOf(s.end, end)
            if (a >= b) continue
            if (a > pos) runs += Run(pos, a, base)
            runs += Run(a, b, s.fps)
            pos = b
        }
        if (pos < end) runs += Run(pos, end, base)

        val out = mutableListOf<Piece>()
        var t = Rational.ZERO
        for (r in runs) {
            val prev = out.lastOrNull()
            if (prev != null && prev.rate == r.rate) {         // adjacent runs with the same rate
                out[out.lastIndex] = prev.copy(end = r.b)
            } else {
                out += Piece(r.a, r.b, r.rate, t)
            }
            t += Rational.of((r.b - r.a).toLong()) / r.rate
        }
        return out
    }

    /** Output seconds of a speed ramp (user: 0.5 s, centred on the border). */
    val RAMP_SECONDS: Rational = Rational.of(1, 2)
    /** A ramp is played as this many steps of equal output length, each with its own rate. */
    const val RAMP_STEPS = 10

    /** Borders (frame positions) marked smooth by a section's smoothStart / smoothEnd. */
    fun smoothBorders(segments: List<Segment>): Set<Int> =
        segments.flatMap { listOfNotNull(it.start.takeIf { _ -> it.smoothStart }, it.end.takeIf { _ -> it.smoothEnd }) }.toSet()

    /**
     * Speed ramps at the smooth borders of [segments] within [start, end) (gaps at [base]): the
     * rate changes linearly in output time over [RAMP_SECONDS], centred on the border, played as
     * [RAMP_STEPS] sections. A side shorter than twice its share shortens the whole ramp. Exact
     * rational arithmetic with half-even rounding – the desktop computes the same frames.
     * [encodeAt] (smart export): the steps are re-encoded at this rate.
     */
    fun rampSteps(segments: List<Segment>, start: Int, end: Int, base: Rational, encodeAt: Rational? = null): List<Segment> {
        val smooth = smoothBorders(segments)
        if (smooth.isEmpty()) return emptyList()
        val ps = pieces(segments, start, end, base)
        val steps = mutableListOf<Segment>()
        val n = Rational.of(RAMP_STEPS.toLong())
        for (i in 0 until ps.size - 1) {
            val border = ps[i].end
            if (border !in smooth) continue
            val ra = ps[i].rate
            val rb = ps[i + 1].rate
            // source frames used before / after the border for a ramp of t seconds
            val before = { t: Rational -> t * (ra * 3 + rb) / 8 }
            val after = { t: Rational -> t * (ra + rb * 3) / 8 }
            val halfA = Rational.of((ps[i].end - ps[i].start).toLong(), 2)
            val halfB = Rational.of((ps[i + 1].end - ps[i + 1].start).toLong(), 2)
            val scale = minOf(Rational.ONE, halfA / before(RAMP_SECONDS), halfB / after(RAMP_SECONDS))
            val t = RAMP_SECONDS * scale
            val a = border - before(t).roundHalfEven().toInt()
            val b = border + after(t).roundHalfEven().toInt()
            if (b <= a) continue
            // frames played by the end of step k: integral of the linear rate, as a share of all
            val mean = (ra + rb) / 2
            fun pos(k: Int): Int {
                val x = Rational.of(k.toLong()) / n
                val share = (x * ra + (rb - ra) * x * x / 2) / mean
                return a + (share * (b - a).toLong()).roundHalfEven().toInt()
            }
            for (k in 0 until RAMP_STEPS) {
                val p0 = pos(k)
                val p1 = pos(k + 1)
                if (p1 <= p0) continue
                val rate = ra + (rb - ra) * Rational.of((2 * k + 1).toLong()) / (n * 2)
                steps += Segment(p0, p1, rate, encodeAt != null, encodeAt)
            }
        }
        return steps
    }

    /** [target] with the ramp [steps] laid over it (steps win, like added sections). */
    fun withRamps(target: List<Segment>, steps: List<Segment>): List<Segment> = steps.fold(target) { acc, s -> add(acc, s) }

    fun duration(ps: List<Piece>): Rational {
        val last = ps.lastOrNull() ?: return Rational.ZERO
        return last.t + Rational.of((last.end - last.start).toLong()) / last.rate
    }

    /** Output time (seconds) at which source frame [frame] starts. */
    fun outputTime(ps: List<Piece>, frame: Int): Rational {
        for (p in ps) {
            if (frame < p.end) return p.t + Rational.of(maxOf(0, frame - p.start).toLong()) / p.rate
        }
        return duration(ps)
    }

    /** Source frame shown at output time [t] (seconds). */
    fun sourceFrame(ps: List<Piece>, t: Double): Int {
        var i = ps.indexOfLast { it.t.toDouble() <= t }
        if (i < 0) i = 0
        val p = ps[i]
        return minOf(p.end - 1, p.start + ((t - p.t.toDouble()) * p.rate.toDouble() + 1e-9).toInt())
    }

    /**
     * New presentation time (µs, relative to the first copied frame) of every source frame –
     * the stream-copy retime. Equivalent to the desktop's `setts_expr`: between section borders
     * the mapping is linear in the *source* times (so source jitter is kept, scaled), and every
     * border lands exactly on its output time.
     *
     * [times] are the source frames' presentation times in seconds (display order; exact for
     * constant-rate sources, see [FrameMap.exactTimes]), [end] the end time of the last frame.
     * Returns a function from a frame index to the output timestamp.
     */
    fun retimer(ps: List<Piece>, times: Array<Rational>, end: Rational): (Int) -> Long {
        val x0 = times[ps.first().start]
        val bordersIn = Array(ps.size) { times[ps[it].start] - x0 }
        val ends = Array(ps.size) { i ->
            val e = ps[i].end
            (if (e < times.size) times[e] else end) - x0
        }
        val million = Rational.of(1_000_000)
        val slopes = Array(ps.size) { i ->
            val p = ps[i]
            val outLen = Rational.of((p.end - p.start).toLong()) / p.rate
            val inLen = ends[i] - bordersIn[i]
            if (inLen > Rational.ZERO) outLen / inLen else Rational.ZERO
        }
        val half = Rational.of(1, 2)
        return { frame ->
            val x = times[frame] - x0
            var i = ends.indexOfFirst { x < it }
            if (i < 0) i = ps.lastIndex
            val out = ps[i].t + slopes[i] * (x - bordersIn[i])
            (out * million + half).floor()          // round half up to whole µs
        }
    }
}
