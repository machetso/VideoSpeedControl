package com.alexvulcu.videospeedcontrol.core

import org.junit.Assert.assertEquals
import org.junit.Test

class RationalTest {
    @Test fun parseAndPrintLikePython() {
        assertEquals("30000/1001", Rational.parse("30000/1001").toString())
        assertEquals("30", Rational.parse("30").toString())
        assertEquals("2997/100", Rational.parse("29.97").toString())
        assertEquals("240", Rational.parse("480/2").toString())
    }

    @Test fun limitDenominator() {
        assertEquals("30000/1001", Rational.fromDouble(29.97002997).toString())
        assertEquals("240", Rational.fromDouble(239.99999).toString())
        assertEquals("120", Rational.fromDouble(120.0).toString())
    }

    @Test fun floorRoundsDown() {
        assertEquals(2L, Rational.of(5, 2).floor())
        assertEquals(-3L, Rational.of(-5, 2).floor())
    }
}

class SegmentsTest {
    private fun r(s: String) = Rational.parse(s)

    @Test fun addNewWinsOnOverlap() {
        val a = Segment(10, 50, r("30"))
        val out = Segments.add(listOf(a), Segment(20, 30, r("60")))
        assertEquals(listOf(Segment(10, 20, r("30")), Segment(20, 30, r("60")), Segment(30, 50, r("30"))), out)
    }

    @Test fun piecesFillGapsAndMerge() {
        // 240 fps clip, section 100..200 at 30 fps; the rest real time (240)
        val ps = Segments.pieces(listOf(Segment(100, 200, r("30"))), 0, 400, r("240"))
        assertEquals(3, ps.size)
        assertEquals(Piece(0, 100, r("240"), r("0")), ps[0])
        assertEquals(Piece(100, 200, r("30"), r("100/240")), ps[1])
        assertEquals(r("100/240") + r("100/30"), ps[2].t)
        assertEquals(r("100/240") + r("100/30") + r("200/240"), Segments.duration(ps))

        val merged = Segments.pieces(listOf(Segment(0, 10, r("240"))), 0, 20, r("240"))
        assertEquals(1, merged.size)
    }

    @Test fun outputTimeAndSourceFrameRoundTrip() {
        val ps = Segments.pieces(listOf(Segment(100, 200, r("30"))), 0, 400, r("240"))
        for (f in listOf(0, 99, 100, 150, 199, 200, 399)) {
            assertEquals(f, Segments.sourceFrame(ps, Segments.outputTime(ps, f).toDouble()))
        }
    }

    @Test fun retimerHitsBordersExactly() {
        // 240 fps source, timestamps in µs rounded like MediaExtractor gives them → exact grid
        val fm = FrameMap(LongArray(400) { Math.round(it * 1e6 / 240) }, intArrayOf(0))
        val (times, end) = fm.exactTimes(r("240"))
        val ps = Segments.pieces(listOf(Segment(100, 200, r("30"))), 0, 400, r("240"))
        val f = Segments.retimer(ps, times, end)
        assertEquals(0L, f(0))
        assertEquals(Math.round(100 * 1e6 / 240), f(100))                       // section start
        assertEquals(Math.round(100 * 1e6 / 240 + 100 * 1e6 / 30), f(200))      // section end
        assertEquals(Math.round(100 * 1e6 / 240 + 50 * 1e6 / 30), f(150))       // inside: 30 fps
        for (i in 1 until 400) assert(f(i) > f(i - 1))
    }

    @Test fun retimerNoJitterOnConstantRate() {
        // 240 → 25 fps: every frame exactly 40 ms apart despite the µs rounding of the source
        val fm = FrameMap(LongArray(960) { Math.round(it * 1e6 / 240) }, intArrayOf(0))
        val (times, end) = fm.exactTimes(r("240"))
        val f = Segments.retimer(Segments.pieces(emptyList(), 0, 960, r("25")), times, end)
        for (i in 0 until 960) assertEquals(i * 40_000L, f(i))
    }

    @Test fun retimerKeepsRealJitter() {
        // phone-like timestamps that are off the grid: the source's own spacing is kept, scaled
        val pts = LongArray(10) { it * 33_333L + if (it % 2 == 1) 400 else 0 }
        val fm = FrameMap(pts, intArrayOf(0))
        val (times, end) = fm.exactTimes(r("30"))
        val f = Segments.retimer(Segments.pieces(emptyList(), 0, 10, r("15")), times, end)
        // gaps keep their 33733 : 32933 proportion (linear mapping, like the desktop's setts)
        val a = (f(1) - f(0)).toDouble()
        val b = (f(2) - f(1)).toDouble()
        assertEquals(33_733.0 / 32_933.0, a / b, 1e-4)
    }

    @Test fun retimerWithTrimStartsAtZero() {
        val fm = FrameMap(LongArray(100) { it * 10_000L }, intArrayOf(0))   // 100 fps
        val (times, end) = fm.exactTimes(r("100"))
        val ps = Segments.pieces(emptyList(), 20, 60, r("25"))  // whole range slowed to 25 fps
        val f = Segments.retimer(ps, times, end)
        assertEquals(0L, f(20))
        assertEquals(40_000L, f(21))
        assertEquals(1_560_000L, f(59))
    }
}
