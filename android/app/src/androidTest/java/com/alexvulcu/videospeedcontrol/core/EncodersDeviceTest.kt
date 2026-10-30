package com.alexvulcu.videospeedcontrol.core

import android.media.MediaCodecList
import android.media.MediaFormat
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Encoder choice on this phone: AV1 fast only in hardware, size / rate checks before an export. */
@RunWith(AndroidJUnit4::class)
class EncodersDeviceTest {
    private val video = MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos
        .filter { it.isEncoder && it.supportedTypes.any { t -> t.startsWith("video/") } }

    @Test fun listEncoders() {
        for (info in video) {
            Log.i("EncodersDeviceTest", "${info.name} ${info.supportedTypes.joinToString()} " +
                if (info.isHardwareAccelerated) "hardware" else "software")
        }
        for (c in VideoCodec.entries) Log.i("EncodersDeviceTest", "$c available=${Encoders.available(c)}")
    }

    @Test fun av1FastOnlyInHardware() {
        val hardwareAv1 = video.any { MediaFormat.MIMETYPE_VIDEO_AV1 in it.supportedTypes && it.isHardwareAccelerated }
        assertEquals(hardwareAv1, Encoders.available(VideoCodec.AV1_FAST))
        if (Encoders.available(VideoCodec.AV1_FAST)) {
            val f = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AV1, 1920, 1080)
            val name = Encoders.pick(VideoCodec.AV1_FAST, f)
            assertTrue(video.first { it.name == name }.isHardwareAccelerated)
        }
    }

    @Test fun sizeAndRateChecks() {
        assertTrue(Encoders.supports(MediaFormat.MIMETYPE_VIDEO_AVC, 1920, 1080, 30.0))
        assertFalse(Encoders.supports(MediaFormat.MIMETYPE_VIDEO_AVC, 20000, 20000, 30.0))
        for (c in VideoCodec.entries.filter { Encoders.available(it) }) {
            assertFalse("$c 20000²", Encoders.supports(c, 20000, 20000, 30.0))
            // the check agrees with the encoder the export picks
            for ((w, h, fps) in listOf(Triple(1920, 1080, 30.0), Triple(1920, 1080, 240.0), Triple(128, 128, 30.0))) {
                val f = MediaFormat.createVideoFormat(c.mime, w, h).apply { setFloat(MediaFormat.KEY_FRAME_RATE, fps.toFloat()) }
                val picked = Encoders.pick(c, f) != null
                Log.i("EncodersDeviceTest", "$c ${w}×$h @ $fps: ${Encoders.supports(c, w, h, fps)}")
                assertEquals("$c ${w}×$h @ $fps", picked, Encoders.supports(c, w, h, fps))
            }
        }
    }
}
