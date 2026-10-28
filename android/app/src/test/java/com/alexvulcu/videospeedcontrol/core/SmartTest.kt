package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito
import java.nio.ByteBuffer

/** Same cases as the desktop's tests/test_smart.py. */
class SmartTest {
    private fun r(s: String) = Rational.parse(s)

    /** 240 fps clip, 960 frames, keyframe every 24 frames (the desktop's h264 test clip). */
    private fun info(): ClipInfo {
        val fm = FrameMap(LongArray(960) { Math.round(it * 1e6 / 240) }, IntArray(40) { it * 24 })
        return ClipInfo(
            uri = Mockito.mock(Uri::class.java), name = "c.mp4", sizeBytes = 1, videoMime = "video/avc",
            width = 320, height = 180, rotation = 0, durationUs = 4_000_000, fps = r("240"),
            captureFps = null, bitrate = null, hdr = null, audio = null, audioRate = null,
            recorded = null, frames = fm,
        )
    }

    @Test fun planWidensToKeyframes() {
        val info = info()
        val segs = listOf(Segment(30, 40, r("25"), reencode = true, outFps = r("25")),
            Segment(100, 120, r("60")))                                       // copied section
        val job = LosslessJob(info, info.realFps, segments = segs)
        val parts = Smart.plan(job, info.frames.keyframes.toList())
        assertEquals(listOf(Triple(false, 0, 24), Triple(true, 24, 48), Triple(false, 48, 960)),
            parts.map { Triple(it.encode, it.start, it.end) })
    }

    @Test fun encodedPartLastsWholeFrames() {
        val info = info()
        // 40 frames at 8× real speed = 0.0208 s → 1 frame at 25 fps (desktop: max(1, round(…)))
        val job = LosslessJob(info, info.realFps,
            segments = listOf(Segment(0, 40, info.realFps * 8, reencode = true, outFps = r("25"))))
        val p = Smart.plan(job, info.frames.keyframes.toList()).first()
        assertTrue(p.encode)
        assertEquals(0 to 48, p.start to p.end)              // widened to the next keyframe
        assertEquals(r("1/25") * Rational.of(p.frames.toLong()), p.duration)
    }

    @Test fun overlappingRangesMerge() {
        val info = info()
        val segs = listOf(Segment(30, 40, r("30"), true, r("30")), Segment(44, 50, r("60"), true, r("60")))
        val ranges = Smart.encodeRanges(segs, Trim(), 960, info.frames.keyframes.toList())
        assertEquals(listOf(Triple(24, 72, r("30"))), ranges)  // merged, first section's fps kept
    }

    @Test fun openGopOnlyIdrIsSafe() {
        val joins = listOf(0)                                     // analysis found only the IDR
        val info = info()
        val job = LosslessJob(info, info.realFps, trim = Trim(0, 60),
            segments = listOf(Segment(30, 40, r("30"), true, r("30"))))
        assertEquals(listOf(Triple(true, 0, 60)), Smart.plan(job, joins).map { Triple(it.encode, it.start, it.end) })
    }

    @Test fun roundingIsHalfEvenLikePython() {
        assertEquals(2L, Rational.parse("5/2").roundHalfEven())
        assertEquals(4L, Rational.parse("7/2").roundHalfEven())
        assertEquals(3L, Rational.parse("29/10").roundHalfEven())
    }

    private fun sample(vararg nals: Pair<Int, Boolean>, hevc: Boolean): ByteBuffer {
        val b = ByteBuffer.allocate(256)
        for ((t, _) in nals) {
            val header = if (hevc) byteArrayOf((t shl 1).toByte(), 1) else byteArrayOf((0x60 or t).toByte())
            val payload = byteArrayOf(0x80.toByte(), 0x11, 0x22)
            b.putInt(header.size + payload.size).put(header).put(payload)
        }
        b.flip()
        return b
    }

    @Test fun nalTypesAndSafety() {
        val idr = sample(32 to false, 33 to false, 34 to false, 19 to true, hevc = true)
        assertEquals(listOf(19), Smart.nalTypes(idr, idr.limit(), hevc = true))
        val cra = Smart.nalTypes(sample(21 to true, hevc = true).let { it }, 9, hevc = true)!!
        val rasl = listOf(8)
        assertTrue(Smart.safe(listOf(19), null, hevc = true))
        assertTrue(Smart.safe(cra, listOf(1), hevc = true))
        assertFalse(Smart.safe(cra, rasl, hevc = true))                  // open GOP
        val h264 = sample(7 to false, 8 to false, 5 to true, hevc = false)
        assertEquals(listOf(5), Smart.nalTypes(h264, h264.limit(), hevc = false))
        assertTrue(Smart.safe(listOf(5), null, hevc = false))
        assertFalse(Smart.safe(listOf(1), null, hevc = false))
        assertNull(Smart.nalTypes(idr, idr.limit() - 1, hevc = true))   // lengths don't add up
    }

    @Test fun annexBFromMediaExtractor() {
        // what MediaExtractor gives for MP4: start codes, several NAL units per sample
        val b = ByteBuffer.allocate(64)
        for (t in listOf(35, 39, 19, 19)) {                // AUD, SEI, IDR in two slices
            b.put(byteArrayOf(0, 0, 0, 1, (t shl 1).toByte(), 1, 0x80.toByte(), 0x55, 0x00, 0x00, 0x03, 0x01))
        }
        b.flip()
        assertEquals(listOf(19, 19), Smart.nalTypes(b, b.limit(), hevc = true))
        val h = ByteBuffer.wrap(byteArrayOf(0, 0, 1, 0x09, 0x10, 0, 0, 1, 0x65, 0x88.toByte(), 0x80.toByte()))
        assertEquals(listOf(5), Smart.nalTypes(h, h.limit(), hevc = false))
    }

    private data class Case(val segs: List<Segment>, val trim: Trim, val joins: List<Int>, val want: List<String>)

    /** Random section layouts planned by the desktop (smart.plan) – Android must plan the same. */
    @Test fun samePlansAsTheDesktop() {
        val cases = listOf(
        Case(listOf(Segment(39, 145, r("480"), true, null), Segment(191, 210, r("120"), true, null), Segment(265, 377, r("24000/1001"), true, r("60")), Segment(384, 533, r("24000/1001"), false, null)), Trim(48, null), listOf(24, 72, 96, 120, 144, 192, 216, 240, 264, 288, 312, 336, 360, 384, 408, 432, 456, 480, 504, 552, 576, 600, 624, 696, 744, 768, 816, 840, 864, 888, 936),
            listOf("encode 48-216 17 17/30", "copy 216-264 48 1/5", "encode 264-384 282 47/10", "copy 384-960 576 191849/24000")),
        Case(listOf(Segment(96, 188, r("480"), true, r("60")), Segment(262, 383, r("24000/1001"), false, r("30")), Segment(443, 464, r("24000/1001"), false, r("30")), Segment(537, 656, r("30"), false, r("30"))), Trim(0, 936), listOf(0, 24, 48, 72, 96, 144, 192, 216, 240, 264, 288, 312, 336, 408, 432, 456, 480, 504, 528, 552, 600, 624, 648, 672, 696, 720, 744, 816, 864, 936),
            listOf("copy 0-96 96 2/5", "encode 96-192 12 1/5", "copy 192-936 744 47607/4000")),
        Case(listOf(Segment(85, 191, r("60"), true, r("60")), Segment(242, 262, r("25"), true, r("25")), Segment(318, 364, r("24000/1001"), true, null), Segment(377, 382, r("120"), true, null)), Trim(24, null), listOf(0, 24, 48, 72, 120, 144, 168, 192, 240, 264, 288, 360, 384, 408, 432, 480, 504, 576, 600, 624, 672, 720, 744, 768, 792, 816, 840, 912, 936),
            listOf("copy 24-72 48 1/5", "encode 72-192 110 11/6", "copy 192-240 48 1/5", "encode 240-264 20 4/5", "copy 264-288 24 1/10", "encode 288-384 64 32/15", "copy 384-960 576 12/5")),
        Case(listOf(Segment(54, 110, r("120"), true, null), Segment(113, 189, r("60"), true, r("30")), Segment(246, 340, r("30"), true, null), Segment(369, 494, r("25"), true, r("60"))), Trim(0, 936), listOf(24, 48, 96, 120, 168, 216, 240, 264, 336, 384, 408, 456, 480, 504, 528, 552, 576, 600, 648, 672, 696, 768, 816, 864, 912, 936),
            listOf("copy 0-48 48 1/5", "encode 48-216 56 28/15", "copy 216-240 24 1/10", "encode 240-504 250 25/3", "copy 504-936 432 9/5")),
        Case(listOf(Segment(62, 150, r("30"), true, r("25")), Segment(157, 252, r("60"), false, r("60")), Segment(316, 354, r("120"), true, null), Segment(410, 461, r("120"), true, r("25"))), Trim(0, null), listOf(0, 48, 72, 96, 120, 168, 192, 216, 240, 288, 312, 384, 408, 432, 456, 480, 504, 528, 552, 600, 672, 696, 768, 792, 816, 840, 864, 888, 912),
            listOf("copy 0-48 48 1/5", "encode 48-168 80 16/5", "copy 168-312 144 33/20", "encode 312-384 14 7/15", "copy 384-408 24 1/10", "encode 408-480 13 13/25", "copy 480-960 480 2")),
        Case(listOf(Segment(76, 174, r("25"), true, r("25")), Segment(233, 294, r("480"), false, r("60")), Segment(356, 402, r("480"), false, r("25")), Segment(457, 593, r("60"), true, r("25"))), Trim(24, 720), listOf(0, 24, 48, 72, 120, 144, 168, 216, 264, 312, 336, 384, 480, 528, 552, 576, 600, 624, 648, 696, 744, 768, 792, 816, 840, 864, 888, 912, 936),
            listOf("copy 24-72 48 1/5", "encode 72-216 103 103/25", "copy 216-384 168 247/480", "encode 384-600 64 64/25", "copy 600-720 120 1/2")),
        Case(listOf(Segment(88, 161, r("120"), true, r("25")), Segment(175, 221, r("30"), true, r("25")), Segment(260, 343, r("120"), false, r("30")), Segment(400, 533, r("480"), true, r("30"))), Trim(0, 720), listOf(0, 24, 48, 96, 120, 144, 168, 192, 216, 240, 312, 336, 360, 384, 456, 552, 576, 624, 648, 672, 696, 720, 768, 792, 816, 840, 864, 888, 912, 936),
            listOf("copy 0-48 48 1/5", "encode 48-240 61 61/25", "copy 240-384 144 227/240", "encode 384-552 13 13/30", "copy 552-720 168 7/10")),
        Case(listOf(Segment(76, 143, r("24000/1001"), false, r("30")), Segment(170, 266, r("25"), true, r("60")), Segment(276, 402, r("30"), true, r("25")), Segment(433, 567, r("1920"), true, r("30"))), Trim(0, null), listOf(0, 24, 48, 72, 96, 120, 144, 192, 264, 288, 336, 384, 408, 480, 552, 576, 600, 696, 744, 768, 792, 816, 840, 864, 888, 936),
            listOf("copy 0-144 144 74767/24000", "encode 144-576 506 253/30", "copy 576-960 384 8/5")),
        Case(listOf(Segment(42, 183, r("480"), true, r("30")), Segment(183, 304, r("1920"), true, null), Segment(371, 392, r("480"), false, r("30")), Segment(401, 473, r("25"), false, r("25"))), Trim(0, 936), listOf(0, 24, 48, 72, 120, 144, 168, 192, 216, 264, 288, 312, 336, 360, 384, 408, 432, 456, 480, 504, 528, 552, 600, 672, 696, 768, 792, 816, 864, 888, 912, 936),
            listOf("copy 0-24 24 1/10", "encode 24-312 14 7/15", "copy 312-936 624 4109/800")),
        Case(listOf(Segment(39, 174, r("30"), false, r("30")), Segment(203, 335, r("60"), true, r("25")), Segment(335, 465, r("480"), true, r("30")), Segment(483, 594, r("30"), true, null)), Trim(24, null), listOf(0, 24, 48, 96, 120, 168, 192, 216, 264, 360, 384, 408, 432, 456, 504, 528, 600, 624, 672, 720, 744, 768, 816, 840, 864, 912),
            listOf("copy 24-192 168 371/80", "encode 192-600 158 158/25", "copy 600-960 360 3/2")),
        Case(listOf(Segment(51, 99, r("60"), true, r("30")), Segment(137, 207, r("480"), false, r("30")), Segment(258, 324, r("30"), true, r("60")), Segment(339, 386, r("480"), true, r("25"))), Trim(48, null), listOf(0, 24, 72, 96, 120, 144, 168, 192, 216, 264, 288, 336, 384, 408, 456, 480, 504, 528, 552, 624, 672, 696, 720, 744, 816, 840, 936),
            listOf("encode 48-120 27 9/10", "copy 120-216 96 61/240", "encode 216-408 158 79/30", "copy 408-960 552 23/10")),
        Case(listOf(Segment(54, 194, r("1920"), true, r("60")), Segment(225, 257, r("25"), true, null), Segment(315, 341, r("120"), false, null), Segment(357, 421, r("120"), false, r("30"))), Trim(0, 720), listOf(0, 24, 72, 96, 144, 168, 216, 240, 288, 312, 360, 384, 408, 432, 456, 480, 504, 528, 576, 600, 624, 648, 672, 696, 720, 768, 792, 816, 840, 888, 912, 936),
            listOf("copy 0-24 24 1/10", "encode 24-288 104 26/15", "copy 288-720 432 87/40")),
        )
        val info = info()
        for ((i, c) in cases.withIndex()) {
            val job = LosslessJob(info, info.realFps, c.trim, c.segs)
            val got = Smart.plan(job, c.joins).map {
                "${if (it.encode) "encode" else "copy"} ${it.start}-${it.end} ${it.frames} ${it.duration}"
            }
            assertEquals("case $i", c.want, got)
        }
    }
}
