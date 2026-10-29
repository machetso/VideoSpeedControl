package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import kotlin.math.abs

/** Re-encode on the phone. Outputs of synthetic clips stay in cache/out for the PSNR check. */
@RunWith(AndroidJUnit4::class)
class ReencodeDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val outDir = File(ctx.cacheDir, "out").apply { mkdirs() }

    private fun export(job: ReencodeJob, name: String, sound: Boolean = false): ClipInfo {
        val out = File(outDir, name)
        val t0 = System.nanoTime()
        val n = FileOutputStream(out).use { ReencodeExport(ctx, job, sound).run(it.fd) }
        Log.i("VscReencode", "$name: $n frames in ${"%.2f".format((System.nanoTime() - t0) / 1e9)} s")
        assertEquals(job.outputFrameCount, n)
        val info = Probe.probe(ctx, Uri.fromFile(out))
        assertEquals(job.outputFrameCount, info.frames.count)
        // constant frame rate: frame k at k / fps (within one 90 kHz tick)
        val step = 1e6 / job.fps.toDouble()
        val p0 = info.frames.ptsUs[0]
        info.frames.ptsUs.forEachIndexed { k, p ->
            assertTrue("frame $k at ${p - p0} µs", abs(p - p0 - k * step) <= 12)
        }
        return info
    }

    @Test fun sections240to60() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_hevc240.mp4")))
        val job = ReencodeJob(info, Rational.of(60), segments = listOf(Segment(240, 480, Rational.of(30))),
            codec = VideoCodec.HEVC)
        export(job, "re_sections60.mp4")                      // 1 + 8 + 2 s = 11 s → 660 frames
        assertEquals(660, job.outputFrameCount)
    }

    @Test fun everyFrameOnceTrimmedAvc() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_hevc240.mp4")))
        // frame-exact trim (not on keyframes), every frame once at 30 fps, 720p → 480p
        val job = ReencodeJob(info, Rational.of(30), trim = Trim(101, 251), codec = VideoCodec.AVC, shortSide = 480)
        val out = export(job, "re_trim30.mp4")
        assertEquals(854, out.width)
        assertEquals(480, out.height)
    }

    @Test fun rotatedBecomesUpright() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_avc120_rot.mp4")))
        val job = ReencodeJob(info, Rational.of(30), speedSetting = Rational.ONE)   // real time
        val out = export(job, "re_rot.mp4")
        assertEquals(0, out.rotation)
        assertEquals(720, out.width)
        assertEquals(1280, out.height)
    }

    @Test fun slowmoWithSound() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_slowmo.mp4")))
        val job = ReencodeJob(info, Rational.of(30), speedSetting = Rational.of(1, 2))   // half speed: 4 s
        export(job, "re_slowmo.mp4", sound = true)
        assertEquals(Rational.of(4), job.outputDuration)
    }

    @Test fun pixelRealTime60() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("PXL_20261025_152730266.mp4")))
        val job = ReencodeJob(info, Rational.of(60), segments = listOf(Segment(300, 600, Rational.of(30))))
        export(job, "re_pixel.mp4", sound = true)
        File(outDir, "re_pixel.mp4").delete()                 // private footage: not pulled
    }

    /** AV1 fast (hardware) with a speed ramp from 8× slower to real time, with sound. */
    @Test fun av1FastWithRamp() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_slowmo.mp4")))
        val segs = rampedSegments(listOf(Segment(0, 120, info.fps, smoothEnd = true)), Trim(), info)
        assertTrue(segs.size > 5)                                       // the ramp steps are in
        val job = ReencodeJob(info, Rational.of(30), segments = segs, codec = VideoCodec.AV1_FAST)
        val out = export(job, "re_av1_fast.mp4", sound = true)
        assertEquals("video/av01", out.videoMime)
    }

    /** AV1 best (software, highest complexity), short and small. */
    @Test fun av1Best() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_hevc240.mp4")))
        val job = ReencodeJob(info, Rational.of(30), trim = Trim(0, 60), codec = VideoCodec.AV1_BEST, shortSide = 480)
        val out = export(job, "re_av1_best.mp4")
        assertEquals("video/av01", out.videoMime)
    }

    /** Lossless with a ramp: every frame kept, timestamps rising, length as computed. */
    @Test fun losslessWithRamp() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_hevc240.mp4")))
        val segs = rampedSegments(listOf(Segment(240, 480, Rational.of(30), smoothStart = true, smoothEnd = true)), Trim(), info)
        val job = LosslessJob(info, Rational.of(30), Trim(), segs)
        val out = File(outDir, "lossless_ramp.mp4")
        val n = FileOutputStream(out).use { LosslessExport(ctx, job).run(it.fd) }
        assertEquals(info.frames.count, n)
        val o = Probe.probe(ctx, Uri.fromFile(out))
        val p = o.frames.ptsUs
        for (k in 1 until p.size) assertTrue("frame $k", p[k] > p[k - 1])
        val want = job.outputDuration.toDouble() * 1e6
        val got = (p.last() - p.first()) + (p.last() - p[p.size - 2])
        assertTrue("length $got µs, want $want", abs(got - want) < 10_000)
    }
}
