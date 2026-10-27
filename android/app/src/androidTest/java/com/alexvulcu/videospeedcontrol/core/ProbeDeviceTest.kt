package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Checks Probe against values the desktop core (ffprobe) reported for the same clip.
 * Test clips are not in the repo; tools/device_test.sh pushes them to /data/local/tmp/vsc/.
 * Missing clips are skipped.
 */
@RunWith(AndroidJUnit4::class)
class ProbeDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext

    private fun clip(name: String): Uri = Uri.fromFile(TestClips.get(name))

    /** Pixel 10 Pro slow-mo, 120 fps capture stored at 30 fps (desktop: fps 30, capture 120). */
    @Test fun pixelSlowmo120() {
        val info = Probe.probe(ctx, clip("PXL_20261025_152730266.mp4"))
        assertEquals("HEVC", info.codecName)
        assertEquals(1920, info.width)
        assertEquals(1080, info.height)
        assertEquals(Rational.of(30), info.fps)
        assertEquals(Rational.of(120), info.captureFps)
        assertEquals(4.0, info.slowmoFactor!!, 1e-9)
        assertEquals(Rational.of(120), info.realFps)
        assertEquals(903, info.frames.count)
        assertEquals(31, info.frames.keyframes.size)
        assertEquals(48000, info.audioRate)
        assertEquals("PXL_20261025_152730266.mp4", info.name)
    }
}
