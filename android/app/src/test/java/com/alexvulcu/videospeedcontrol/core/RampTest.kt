package com.alexvulcu.videospeedcontrol.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Speed ramps – expected frames computed by the desktop's segments.ramp_steps. */
class RampTest {
    private fun r(s: String) = Rational.parse(s)

    @Test fun sameStepsAsTheDesktop() {
        val segs = listOf(
            Segment(100, 300, r("25"), smoothEnd = true),
            Segment(300, 400, r("60"), smoothEnd = true),
            Segment(500, 520, r("30"), smoothStart = true),
        )
        val want = """
            292 293 107/4|293 295 121/4|295 296 135/4|296 298 149/4|298 300 163/4|300 303 177/4|303 305 191/4|
            305 307 205/4|307 310 219/4|310 313 233/4|374 377 69|377 382 87|382 387 105|387 393 123|393 400 141|
            400 408 159|408 417 177|417 427 195|427 437 213|437 449 231|477 483 459/2|483 488 417/2|488 492 375/2|
            492 496 333/2|496 500 291/2|500 503 249/2|503 505 207/2|505 508 165/2|508 509 123/2|509 510 81/2
        """.trimIndent().replace("\n", "").split("|")
        val got = Segments.rampSteps(segs, 0, 600, r("240")).map { "${it.start} ${it.end} ${it.fps}" }
        assertEquals(want, got)
    }

    @Test fun rampsKeepTheTimingConsistent() {
        val segs = listOf(Segment(100, 300, r("25"), smoothEnd = true))
        val steps = Segments.rampSteps(segs, 0, 600, r("240"), encodeAt = r("25"))
        assertTrue(steps.all { it.reencode && it.outFps == r("25") })
        val all = Segments.withRamps(segs, steps)
        // continuous coverage, the section shrunk to where the ramp begins
        assertEquals(100, all.first().start)
        assertEquals(steps.first().start, all.first().end)
        all.zipWithNext().forEach { (a, b) -> assertTrue(a.end <= b.start) }
        // no smooth border → nothing changes
        assertEquals(emptyList<Segment>(), Segments.rampSteps(listOf(Segment(100, 300, r("25"))), 0, 600, r("240")))
    }

    @Test fun cuttingASectionDropsTheFlagAtTheCut() {
        val s = Segment(100, 300, r("25"), smoothStart = true, smoothEnd = true)
        val out = Segments.add(listOf(s), Segment(150, 200, r("60")))
        assertEquals(listOf(
            Segment(100, 150, r("25"), smoothStart = true),
            Segment(150, 200, r("60")),
            Segment(200, 300, r("25"), smoothEnd = true),
        ), out)
    }
}
