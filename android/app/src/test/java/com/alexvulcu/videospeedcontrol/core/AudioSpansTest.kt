package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.mockito.Mockito

class AudioSpansTest {
    private fun info(): ClipInfo {
        val fm = FrameMap(LongArray(960) { Math.round(it * 1e6 / 240) }, IntArray(20) { it * 48 })
        return ClipInfo(
            uri = Mockito.mock(Uri::class.java), name = "c.mp4", sizeBytes = 1, videoMime = "video/hevc",
            width = 1920, height = 1080, rotation = 0, durationUs = 4_000_000, fps = Rational.of(240),
            captureFps = null, bitrate = null, hdr = null, audio = "AAC", audioRate = 48000,
            recorded = null, frames = fm,
        )
    }

    @Test fun reencodedSoundEndsWithTheLastFrame() {
        // 37 frames at 70 fps is not a whole number of 1/30 s frames
        val job = ReencodeJob(info(), Rational.of(30), segments = listOf(Segment(10, 47, Rational.of(70))))
        val total = Audio.spans(job).sumOf { it.out }
        assertNotEquals(job.outputDuration.toDouble(), job.outputFrameCount / 30.0, 1e-9)
        assertEquals(job.outputFrameCount / 30.0, total, 1e-9)
    }

    @Test fun losslessSpansFollowThePieces() {
        val job = LosslessJob(info(), Rational.of(240), segments = listOf(Segment(10, 47, Rational.of(70))))
        assertEquals(job.outputDuration.toDouble(), Audio.spans(job).sumOf { it.out }, 1e-9)
    }
}
