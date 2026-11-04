package com.alexvulcu.videospeedcontrol.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

/** The MKV writer's building blocks (2026-11-04). Byte layouts checked against the Matroska / ISO specs. */
class MkvTest {
    private fun hex(s: String) = s.split(" ").filter { it.isNotEmpty() }.map { it.toInt(16).toByte() }.toByteArray()

    @Test fun ebmlNumbers() {
        assertArrayEquals(hex("81"), Mkv.size(1))
        assertArrayEquals(hex("40 7f"), Mkv.size(127))              // 0x7f alone would be "unknown"
        assertArrayEquals(hex("40 80"), Mkv.size(128))
        assertArrayEquals(hex("01 00 00 00 00 00 01 00"), Mkv.size8(256))
        assertArrayEquals(hex("00"), Mkv.uint(0))
        assertArrayEquals(hex("0f 42 40"), Mkv.uint(1_000_000))
        assertArrayEquals(hex("1a 45 df a3"), Mkv.id(Mkv.EBML))
        assertArrayEquals(hex("a3"), Mkv.id(Mkv.SIMPLE_BLOCK))
    }

    @Test fun voidHasExactSize() {
        for (n in listOf(2, 9, 96, 128, 129, 200)) assertEquals(n, Mkv.void(n).size)
    }

    @Test fun simpleBlock() {
        // track 1, -2 ms relative, keyframe, 3 bytes
        assertArrayEquals(hex("a3 87 81 ff fe 80 01 02 03"), Mkv.simpleBlock(1, -2, true, hex("01 02 03")))
    }

    @Test fun annexBToLengths() {
        val frame = hex("00 00 00 01 65 aa bb 00 00 01 41 cc")
        assertArrayEquals(hex("00 00 00 03 65 aa bb 00 00 00 02 41 cc"), Mkv.lengthPrefixed(frame))
    }

    @Test fun av1TemporalDelimiterRemoved() {
        // the Pixel's encoder output: TD (12 00), sequence header OBU (0a 0b …)
        val tu = hex("12 00 0a 02 aa bb 32 01 cc")
        assertArrayEquals(hex("0a 02 aa bb 32 01 cc"), Mkv.withoutTemporalDelimiters(tu))
    }

    @Test fun avcCFromPixelCsd() {
        val sps = hex("67 64 00 0c ac d2 05 c6 e9 a8 10 10 10 3c 20 10 a8")      // c2.google.avc.encoder
        val pps = hex("68 ea 8f 2c")
        val c = Mkv.avcC(sps, pps)
        assertArrayEquals(hex("01 64 00 0c ff e1 00 11"), c.copyOfRange(0, 8))
        assertEquals(8 + sps.size + 3 + pps.size + 4, c.size)            // High profile: 4 extra bytes
    }

    @Test fun hvcCFromSps() {
        // VPS / SPS / PPS like the Pixel's HEVC encoder (Main, level 2: profile_tier_level from the SPS)
        val vps = hex("40 01 0c 01 ff ff 01 60 00 00 03 00 00 03 00 00 03 00 00 03 00 3c ac 09")
        val sps = hex("42 01 01 01 60 00 00 03 00 00 03 00 00 03 00 00 03 00 3c a0 0b 88 05 a1 63 6b 92 45")
        val pps = hex("44 01 c1 72 b4 62 40")
        val c = Mkv.hvcC(listOf(vps, sps, pps))
        assertEquals(1, c[0].toInt())
        assertEquals(0x01, c[1].toInt())                                  // profile_space 0, tier 0, profile Main
        assertEquals(0x3c, c[12].toInt() and 0xFF)                        // level_idc 60 = 2.0
        assertEquals(3, c[21].toInt() and 0x03)                           // lengthSizeMinusOne
        assertEquals(3, c[22].toInt())                                    // 3 arrays
    }

    @Test fun opusHeadUnwrapped() {
        val head = "OpusHead".toByteArray() + hex("01 02 38 01 80 bb 00 00 00 00 00")
        val wrapped = "AOPUSHDR".toByteArray() + hex("13 00 00 00 00 00 00 00") + head + "AOPUSDLY".toByteArray() + ByteArray(16)
        assertArrayEquals(head, Mkv.unwrapOpusHead(wrapped))
        assertArrayEquals(head, Mkv.unwrapOpusHead(head))
    }
}
