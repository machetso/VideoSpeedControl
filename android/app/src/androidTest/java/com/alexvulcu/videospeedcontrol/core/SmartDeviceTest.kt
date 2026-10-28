package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Safe join points on the phone = what the desktop's smart.join_points finds for the same clips. */
@RunWith(AndroidJUnit4::class)
class SmartDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext

    private fun joins(name: String): Pair<ClipInfo, List<Int>> {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get(name)))
        return info to Smart.joinPoints(ctx, info)
    }

    @Test fun hevcOpenGopOnlyIdr() = assertEquals(listOf(0), joins("synth_hevc240.mp4").second)

    @Test fun h264ClosedGopAllKeyframes() {
        val (info, j) = joins("synth_avc120_rot.mp4")
        assertEquals(listOf(0, 60, 120, 180, 240, 300), j)
        assertEquals(info.frames.keyframes.toList(), j)
    }

    /** Pixel HEVC slow-mo: closed GOPs (IDR every 30 frames, see NalSurveyTest) → all keyframes. */
    @Test fun pixelAllKeyframes() {
        val (info, j) = joins("PXL_20261025_152730266.mp4")
        Log.i("VscSmart", "Pixel: ${j.size} of ${info.frames.keyframes.size} keyframes are safe joins")
        assertTrue(j.isNotEmpty())
        assertEquals(info.frames.keyframes.toList(), j)
    }

    private fun export(name: String, segs: List<Segment>, out: String, sound: Boolean = false): Pair<SmartJob, ClipInfo> {
        val (info, joins) = joins(name)
        val job = SmartJob(info, info.realFps, segments = segs, joins = joins)
        val file = java.io.File(java.io.File(ctx.cacheDir, "out").apply { mkdirs() }, out)
        val t0 = System.nanoTime()
        val n = java.io.FileOutputStream(file).use { SmartExport(ctx, job, sound).run(it.fd) }
        Log.i("VscSmart", "$out: parts ${job.parts.map { "${if (it.encode) "E" else "C"}${it.start}-${it.end}:${it.frames}" }}, " +
            "$n frames in ${"%.2f".format((System.nanoTime() - t0) / 1e9)} s")
        assertEquals(job.parts.sumOf { it.frames }, n)
        val result = Probe.probe(ctx, Uri.fromFile(file))
        assertEquals(n, result.frames.count)
        assertEquals(info.rotation, result.rotation)
        return job to result
    }

    /** H.264, closed GOPs: re-encoded 8× faster part, copied slow-mo, re-encoded slow-mo (desktop test_smart_export). */
    @Test fun smartH264() {
        val real = Rational.of(120)
        export("synth_avc120_rot.mp4", listOf(
            Segment(0, 40, real * 8, reencode = true, outFps = Rational.of(25)),
            Segment(130, 150, Rational.of(25)),
            Segment(190, 230, Rational.of(30), reencode = true, outFps = Rational.of(60)),
        ), "smart_avc.mp4")
    }

    /** Pixel HEVC (parameter sets only in hvcC): the real test of the in-band headers. */
    @Test fun smartPixel() {
        val (job, _) = export("PXL_20261025_152730266.mp4", listOf(
            Segment(30, 90, Rational.of(120), reencode = true, outFps = Rational.of(60)),
            Segment(300, 420, Rational.of(30)),
        ), "smart_pixel.mp4", sound = true)
        assertTrue(job.parts.any { it.encode } && job.parts.any { !it.encode })
    }

    /** Synthetic HEVC with closed GOPs (x265 default is open GOP → re-made below with closed GOPs). */
    @Test fun smartHevcClosed() {
        export("synth_hevc_closed.mp4", listOf(
            Segment(50, 100, Rational.of(30), reencode = true, outFps = Rational.of(30)),
            Segment(300, 400, Rational.of(60)),
            Segment(600, 650, Rational.of(240) * 4, reencode = true, outFps = Rational.of(25)),
        ), "smart_hevc.mp4")
    }
}
