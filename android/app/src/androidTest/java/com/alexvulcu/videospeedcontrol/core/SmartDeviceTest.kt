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

    /** Decode a file with the phone's own decoder; one checksum (sampled luma) per frame. */
    private fun decodeChecksums(file: java.io.File): List<Long> {
        val ex = android.media.MediaExtractor()
        ex.setDataSource(file.path)
        val t = (0 until ex.trackCount).first { ex.getTrackFormat(it).getString(android.media.MediaFormat.KEY_MIME)!!.startsWith("video/") }
        val fmt = ex.getTrackFormat(t)
        ex.selectTrack(t)
        fmt.setInteger(android.media.MediaFormat.KEY_COLOR_FORMAT,
            android.media.MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible)
        val dec = android.media.MediaCodec.createDecoderByType(fmt.getString(android.media.MediaFormat.KEY_MIME)!!)
        dec.configure(fmt, null, null, 0)
        dec.start()
        val sums = mutableListOf<Long>()
        val bi = android.media.MediaCodec.BufferInfo()
        var inDone = false
        try {
            while (true) {
                if (!inDone) {
                    val i = dec.dequeueInputBuffer(10_000)
                    if (i >= 0) {
                        val n = ex.readSampleData(dec.getInputBuffer(i)!!, 0)
                        if (n < 0) { dec.queueInputBuffer(i, 0, 0, 0, android.media.MediaCodec.BUFFER_FLAG_END_OF_STREAM); inDone = true }
                        else { dec.queueInputBuffer(i, 0, n, ex.sampleTime, 0); ex.advance() }
                    }
                }
                val o = dec.dequeueOutputBuffer(bi, 10_000)
                if (o >= 0) {
                    if (bi.size > 0) dec.getOutputImage(o)!!.use { img ->
                        val y = img.planes[0]
                        var sum = 0L
                        for (row in 0 until img.height step 8) for (col in 0 until img.width step 8)
                            sum = sum * 31 + (y.buffer.get(row * y.rowStride + col * y.pixelStride).toInt() and 0xff)
                        sums += sum
                    }
                    dec.releaseOutputBuffer(o, false)
                    if (bi.flags and android.media.MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                }
            }
        } finally {
            dec.stop(); dec.release(); ex.release()
        }
        return sums
    }

    /** The phone's decoder: smart output decodes completely, copied frames = the source's frames. */
    private fun decodesLikeTheSource(source: String, out: String, parts: List<Smart.Part>) {
        val src = decodeChecksums(TestClips.get(source))
        val got = decodeChecksums(java.io.File(java.io.File(ctx.cacheDir, "out"), out))
        assertEquals("decoded frames", parts.sumOf { it.frames }, got.size)
        var pos = 0
        for (p in parts) {
            if (!p.encode) assertEquals("copied ${p.start}-${p.end}", src.subList(p.start, p.end), got.subList(pos, pos + p.frames))
            pos += p.frames
        }
        Log.i("VscSmart", "$out decodes on the phone: ${got.size} frames, copied parts identical")
    }

    @Test fun phoneDecodesSmartOutputs() {
        for ((src, out, segs) in listOf(
            Triple("synth_hevc_closed.mp4", "smart_hevc.mp4", listOf(
                Segment(50, 100, Rational.of(30), reencode = true, outFps = Rational.of(30)),
                Segment(300, 400, Rational.of(60)),
                Segment(600, 650, Rational.of(240) * 4, reencode = true, outFps = Rational.of(25)))),
            Triple("PXL_20261025_152730266.mp4", "smart_pixel.mp4", listOf(
                Segment(30, 90, Rational.of(120), reencode = true, outFps = Rational.of(60)),
                Segment(300, 420, Rational.of(30)))),
        )) {
            val (info, joins) = joins(src)
            val job = SmartJob(info, info.realFps, segments = segs, joins = joins)
            decodesLikeTheSource(src, out, job.parts)
        }
    }

    /** Pixel-like colour description (sRGB transfer): encoded parts must be tagged the same. */
    @Test fun smartKeepsColourDescription() {
        export("synth_pixel_srgb.mp4", listOf(
            Segment(90, 180, Rational.of(25)),                                   // copied at 25p
        ).let { segs ->
            // smart rule: real-time parts (240 ≠ 25) re-encoded at 25 fps
            listOf(Segment(0, 90, Rational.of(240), true, Rational.of(25))) + segs +
                Segment(180, 300, Rational.of(240), true, Rational.of(25))
        }, "smart_srgb.mp4")
    }

    /** A long encoded part (4× slower, 5 s at 25p): keyframes and colour description inside it. */
    @Test fun smartLongEncodedPart() {
        export("synth_pixel_srgb.mp4", listOf(
            Segment(0, 300, Rational.of(60), true, Rational.of(25)),
        ), "smart_long.mp4")
    }

    /** Smart with a speed ramp: 9.6× slower (copied at 25p) easing into real time (encoded). */
    @Test fun smartWithRamp() {
        val (info, joins) = joins("synth_hevc_closed.mp4")
        val fps = Rational.of(25)
        val parts = listOf(
            Segment(0, 442, fps, smoothEnd = true),
            Segment(442, 960, info.realFps, reencode = true, outFps = fps, smoothStart = true),
        )
        val segs = rampedSegments(parts, Trim(), info, fps)
        val job = SmartJob(info, fps, segments = segs, joins = joins)
        val file = java.io.File(java.io.File(ctx.cacheDir, "out").apply { mkdirs() }, "smart_ramp.mp4")
        val n = java.io.FileOutputStream(file).use { SmartExport(ctx, job, true).run(it.fd) }
        Log.i("VscSmart", "smart_ramp: parts ${job.parts.map { "${if (it.encode) "E" else "C"}${it.start}-${it.end}:${it.frames}" }}, $n frames")
        assertEquals(job.parts.sumOf { it.frames }, n)
        val out = Probe.probe(ctx, android.net.Uri.fromFile(file))
        assertEquals(n, out.frames.count)
    }
}
