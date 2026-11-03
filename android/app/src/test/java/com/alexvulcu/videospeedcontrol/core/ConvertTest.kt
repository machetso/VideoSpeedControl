package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito

class ConvertTest {
    /** Like the user's old cartoons: 368×208 DivX at 10 fps, 60 s. */
    private fun divx(): ClipInfo {
        val fm = FrameMap(LongArray(600) { it * 100_000L }, IntArray(6) { it * 100 })
        return ClipInfo(
            uri = Mockito.mock(Uri::class.java), name = "07 - Der Maulwurf als Gärtner.avi.MP.MP4.AVI", sizeBytes = 1,
            videoMime = "video/mp4v-es", width = 368, height = 208, rotation = 0, durationUs = 60_000_000,
            fps = Rational.of(10), captureFps = null, bitrate = null, hdr = null, audio = "MP3 stereo 22.05 kHz",
            audioRate = 22050, recorded = null, frames = fm,
        )
    }

    @Test fun cleanStemDropsVideoExtensions() {
        assertEquals("00 - Der Maulwurf Special", Convert.cleanStem("00 - Der Maulwurf Special.avi.MP4.MP4.AVI"))
        assertEquals("09 - Der Fernseher", Convert.cleanStem("09 - Der Fernseher..MP4.AVI"))
        assertEquals("07 - Der Maulwurf als Gärtner.avi.MP", Convert.cleanStem("07 - Der Maulwurf als Gärtner.avi.MP.MP4.AVI"))
        assertEquals("clip.final", Convert.cleanStem("clip.final.mp4"))
        assertEquals("mp4", Convert.cleanStem(".mp4.avi"))
    }

    @Test fun naturalOrder() = assertEquals(
        listOf("2 - b.avi", "10 - a.avi", "B 3.avi", "b 20.avi"),
        listOf("b 20.avi", "10 - a.avi", "B 3.avi", "2 - b.avi").sortedWith(Convert.naturalOrder),
    )

    @Test fun av1FallsBackToSoftwareThenHevc() {
        // AV1 chip takes the size → hardware
        assertEquals(VideoCodec.AV1_FAST to false, Convert.pickCodec(VideoCodec.AV1_FAST, 1920, 1080, 30.0) { true })
        // too small for the chip (Pixel: ≥ 256 px) → software AV1, fastest setting
        assertEquals(VideoCodec.AV1_BEST to true,
            Convert.pickCodec(VideoCodec.AV1_FAST, 368, 208, 10.0) { it != VideoCodec.AV1_FAST })
        // no AV1 at all → HEVC, else H.264
        assertEquals(VideoCodec.HEVC to false,
            Convert.pickCodec(VideoCodec.AV1_FAST, 368, 208, 10.0) { it == VideoCodec.HEVC || it == VideoCodec.AVC })
        assertEquals(VideoCodec.AVC to false, Convert.pickCodec(VideoCodec.HEVC, 368, 208, 10.0) { it == VideoCodec.AVC })
    }

    @Test fun jobKeepsEverythingWithASmallBitrate() {
        val job = Convert.job(divx(), VideoCodec.AV1_FAST, Quality.HIGH) { c, _, _, _ -> c != VideoCodec.AV1_FAST }
        assertEquals(VideoCodec.AV1_BEST, job.codec)
        assertTrue(job.fastest)
        assertEquals(368 to 208, job.outputSize())
        assertEquals(600, job.outputFrameCount)
        assertEquals(1.0, job.speed.toDouble(), 1e-12)
        assertEquals(200_000, job.bitrate)            // not the editor's 1 Mbit/s floor
        assertEquals(314_285, Convert.job(divx(), VideoCodec.AV1_FAST, Quality.VERY_HIGH) { _, _, _, _ -> true }.bitrate)
    }

    @Test fun taskIsAConversion() {
        val t = Convert.task(7, divx(), VideoCodec.AV1_FAST, Quality.HIGH, sound = true)
        assertTrue(t.treatment.settings.convert)
        assertEquals(Treatment.Mode.REENCODE, t.treatment.settings.mode)
        assertEquals(Rational.of(10), t.treatment.settings.fps)
        assertTrue(t.treatment.settings.sound)
        assertFalse(Convert.task(8, divx().copy(audio = null), VideoCodec.AVC, Quality.GOOD, sound = true).treatment.settings.sound)
    }
}
