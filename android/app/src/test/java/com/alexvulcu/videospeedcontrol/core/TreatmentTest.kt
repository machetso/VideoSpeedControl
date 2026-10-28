package com.alexvulcu.videospeedcontrol.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream

/** .cst compatibility with the desktop (expected values computed by vsc/core/treatment.py). */
class TreatmentTest {
    private fun bytes(size: Int) = ByteArray(size) { (it % 251).toByte() }

    @Test fun fingerprintLikeTheDesktop() {
        for ((size, want) in listOf(
            1000 to "27fced0fcd13304e896beaab3088e259c8d7709a1a70d158c0ec5e55490c173e",
            3 * (1 shl 20) + 123 to "e18b889b3b4020db24ca9eff9ba9b2b13bbb85bd90c92475d868819698ee5bdb",
        )) {
            val data = bytes(size)
            assertEquals(want, Treatment.fingerprint(size.toLong()) { ByteArrayInputStream(data) })
        }
    }

    @Test fun readsADesktopTreatment() {
        val text = javaClass.getResource("/desktop_smart.cst")!!.readText()
        val d = Treatment.fromJson(text, "desktop_smart.cst")
        assertEquals("synth_hevc_closed.mp4", d.sourceName)
        assertEquals(960, d.frames)
        assertEquals(Treatment.Mode.SMART, d.settings.mode)
        assertEquals(Rational.of(25), d.settings.fps)
        assertEquals(Quality.HIGH, d.settings.quality)                 // x265 20 = desktop "High"
        assertEquals(false, d.settings.sound)
        assertEquals(Trim(48, 912), d.trim)
        assertEquals(listOf(
            Segment(50, 100, Rational.of(30), true, Rational.parse("30000/1001")),
            Segment(300, 400, Rational.of(60)),
        ), d.segments)
        assertEquals("source", d.ui.getString("res"))                   // desktop UI keys survive
    }

    @Test fun roundTripKeepsEverything() {
        val d = Treatment.Data("PXL_1.mp4", 1234, "ab".repeat(32), 903,
            Treatment.Settings(Treatment.Mode.REENCODE, Rational.parse("30000/1001"), Rational.of(1, 4),
                VideoCodec.AVC, Quality.VERY_HIGH, 720, sound = true, smartAuto = false, size = 720 to 1280),
            Trim(30, null), listOf(Segment(100, 200, Rational.of(30), false, null)), "content://x")
        val back = Treatment.fromJson(Treatment.toJson(d, "video/hevc"), "x.cst")
        assertEquals(d.copy(ui = back.ui), back)
        val json = Treatment.toJson(d, "video/hevc")
        assertTrue(json.contains("\"codec\": \"x264\""))   // desktop key
        assertTrue(json.contains("\"width\": 720") && json.contains("\"height\": 1280"))
    }

    @Test fun smartWritesTheSourceCodecKey() {
        val d = Treatment.Data("a.mp4", 1, "f", 10, Treatment.Settings(Treatment.Mode.SMART), Trim(), emptyList())
        assertTrue(Treatment.toJson(d, "video/avc").contains("\"codec\": \"x264\""))
        assertTrue(Treatment.toJson(d, "video/hevc").contains("\"codec\": \"x265\""))
    }

    @Test fun refusesOtherFilesAndBrokenOnes() {
        val d = Treatment.fromJson(javaClass.getResource("/desktop_smart.cst")!!.readText(), "d.cst")
        assertThrows(Treatment.TreatmentError::class.java) { d.check("x.mp4", 7561604, "0".repeat(64), 960) }
        assertThrows(Treatment.TreatmentError::class.java) { d.check("x.mp4", d.sourceSize, d.fingerprint, 959) }
        d.check("renamed.mp4", d.sourceSize, d.fingerprint, 960)                     // name does not matter
        assertThrows(Treatment.TreatmentError::class.java) { Treatment.fromJson("{\"format\": \"other\"}", "o.cst") }
        assertThrows(Treatment.TreatmentError::class.java) { Treatment.fromJson("{not json", "b.cst") }
    }
}
