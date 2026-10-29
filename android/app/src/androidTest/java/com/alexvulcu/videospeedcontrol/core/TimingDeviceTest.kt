package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream

/** How long a lossless export with Easy-style sections takes: sound vs. video. -e clip PATH */
@RunWith(AndroidJUnit4::class)
class TimingDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun losslessEasySections() {
        val path = InstrumentationRegistry.getArguments().getString("clip")
        assumeTrue(path != null)
        val info = Probe.probe(ctx, Uri.fromFile(File(path!!)))
        val n = info.frames.count
        val secs = Segments.allSmooth(listOf(Segment(n / 5, 2 * n / 5, Rational.of(25)),
            Segment(2 * n / 5, 3 * n / 5, Rational.of(60)), Segment(3 * n / 4, n - 10, Rational.of(30))))
        for ((label, segs) in listOf("plain" to secs.map { it.copy(smoothStart = false, smoothEnd = false) }, "smooth" to secs)) {
            val job = LosslessJob(info, Rational.of(25), Trim(), rampedSegments(segs, Trim(), info))
            var t0 = System.nanoTime()
            val spans = Audio.spans(job)
            val audio = Audio.render(ctx, job, { false }) {}
            val tAudio = (System.nanoTime() - t0) / 1e9
            t0 = System.nanoTime()
            val out = File(File(ctx.cacheDir, "out").apply { mkdirs() }, "timing.mp4")
            FileOutputStream(out).use { LosslessExport(ctx, job, false).run(it.fd) }
            val tVideo = (System.nanoTime() - t0) / 1e9
            out.delete()
            Log.i("VscTiming", "$label: ${job.segments.size} sections, ${spans.size} sound spans, sound ${"%.1f".format(tAudio)} s " +
                "(${audio?.samples?.size} AAC frames), video ${"%.1f".format(tVideo)} s, output ${"%.1f".format(job.outputDuration.toDouble())} s")
        }
    }
}
