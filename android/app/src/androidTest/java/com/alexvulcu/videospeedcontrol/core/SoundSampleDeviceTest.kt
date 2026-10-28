package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream

/**
 * Listening sample of the app's slow-motion sound: frames 60–660 of PXL_SloMoTest.mp4 (real time
 * 0.25–2.75 s of a 240 fps recording) at 30 fps = 8× slower. Output in cache/out for pulling.
 * Skipped unless the clip was pushed (private footage – only on request).
 */
@RunWith(AndroidJUnit4::class)
class SoundSampleDeviceTest {
    @Test fun slowmo8x() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("PXL_SloMoTest.mp4")))
        val job = LosslessJob(info, info.realFps, segments = listOf(Segment(60, 660, Rational.of(30))))
        val out = File(File(ctx.cacheDir, "out").apply { mkdirs() }, "sample_sonic.mp4")
        FileOutputStream(out).use { LosslessExport(ctx, job, withAudio = true).run(it.fd) }
    }
}
