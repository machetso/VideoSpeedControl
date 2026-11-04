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

    // ------------------------------------------------------------------ pro mode / smart (2026-11-04)
    private fun divxMeasured() = divx().copy(sizeBytes = 4_800_000, audioMime = "audio/mpeg", audioChannels = 2,
        audioBitrate = 96_000, frames = FrameMap(LongArray(600) { it * 100_000L }, IntArray(6) { it * 100 }, bytes = 3_300_000))

    @Test fun measuredVideoRate() = assertEquals(440_000, divxMeasured().videoBitrate)

    @Test fun smartRulesForDivx() {
        val info = divxMeasured()
        val id = Convert.suggest(info, VideoCodec.AV1_FAST, Convert.Goal.IDENTICAL, OutMuxer.Container.MKV)
        assertEquals(387, id.videoKbps)                                   // 440 × 0.88
        assertEquals("copy", id.audio)                                    // MP3 into MKV
        val small = Convert.suggest(info, VideoCodec.AV1_FAST, Convert.Goal.SMALLER, OutMuxer.Container.MP4)
        assertEquals(224, small.videoKbps)                                // 440 × 0.51
        assertEquals(Triple("aac", 64, 2), Triple(small.audio, small.audioKbps, small.channels))  // 96 × 0.85 × 0.8
        // HEVC "looks identical" needs more than the source on the phone → capped, with a note
        val hevc = Convert.suggest(info, VideoCodec.HEVC, Convert.Goal.IDENTICAL, OutMuxer.Container.MKV)
        assertEquals(440, hevc.videoKbps)
        assertTrue(hevc.note.isNotEmpty())
    }

    @Test fun softwareAv1Overshoot() {
        assertEquals(175, Convert.softwareAv1Request(387))                // measured: 200 asked → ~435 real
        assertEquals(30, Convert.softwareAv1Request(50))
    }

    @Test fun audioRules() {
        val info = divxMeasured()
        assertTrue(Convert.audioProblem(info, Convert.Settings(audio = "copy")) != null)          // MP3 into MP4
        assertEquals(null, Convert.audioProblem(info, Convert.Settings(audio = "copy", container = OutMuxer.Container.MKV)))
        assertTrue(Convert.audioProblem(info, Convert.Settings(audio = "opus", container = OutMuxer.Container.MOV)) != null)
        assertTrue(Convert.audioProblem(info, Convert.Settings(audio = "flac")) != null)          // FLAC only in MKV
        assertFalse(OutMuxer.canHoldVideo(OutMuxer.Container.MOV, VideoCodec.AV1_FAST))
    }

    @Test fun settingsJsonRoundTrip() {
        val s = Convert.Settings(codec = VideoCodec.HEVC, container = OutMuxer.Container.MKV, fps = Rational.of(25),
            rate = Convert.Rate.KBPS, kbps = 800, goal = Convert.Goal.SMALLER, audio = "aac", channels = 1, audioKbps = 64)
        assertEquals(s, Convert.Settings.fromJson(org.json.JSONObject(s.toJson().toString())))
        assertEquals(Convert.Settings(), Convert.Settings.fromJson(null))
    }
}
