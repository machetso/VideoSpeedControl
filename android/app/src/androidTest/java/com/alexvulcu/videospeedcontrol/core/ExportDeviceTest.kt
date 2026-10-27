package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import kotlin.math.abs

/**
 * Lossless export on the phone. Outputs stay in the app cache (cache/out/) so tools/
 * device_test.sh can pull them for a frame-by-frame check with the desktop's ffprobe.
 * Synthetic clips (made with the desktop FFmpeg) – see tools/make_test_clips.sh.
 */
@RunWith(AndroidJUnit4::class)
class ExportDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val outDir = File(ctx.cacheDir, "out").apply { mkdirs() }

    private fun export(job: LosslessJob, name: String): Pair<File, ClipInfo> {
        val out = File(outDir, name)
        val n = FileOutputStream(out).use { LosslessExport(ctx, job).run(it.fd) }
        assertEquals(job.sourceFrameCount, n)
        return out to Probe.probe(ctx, Uri.fromFile(out))
    }

    /** Output timestamps must equal the retimer's, within one tick of the MP4 time scale (90 kHz). */
    private fun assertTiming(job: LosslessJob, out: ClipInfo) {
        val (times, end) = job.info.frames.exactTimes(job.info.fps)
        val f = Segments.retimer(job.pieces(), times, end)
        val want = LongArray(job.sourceFrameCount) { f(job.trim.start + it) }
        val got = out.frames.ptsUs.map { it - out.frames.ptsUs[0] }.toLongArray()
        assertEquals(want.size, got.size)
        for (i in want.indices) {
            assertTrue("frame $i: want ${want[i]} µs, got ${got[i]} µs", abs(want[i] - got[i]) <= 12)
        }
    }

    @Test fun hevc240RetimeTo25() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_hevc240.mp4")))
        assertEquals(Rational.of(240), info.fps)
        val job = LosslessJob(info, Rational.of(25))
        val (_, out) = export(job, "hevc240_to25.mp4")
        assertEquals(960, out.frames.count)
        assertEquals(Rational.of(25), out.fps)
        assertArrayEquals(info.frames.keyframes, out.frames.keyframes)
        assertTiming(job, out)
        assertEquals(38.4, out.durationUs / 1e6, 0.05)       // 960 frames / 25 fps
        assertEquals("synth_hevc240_0_104x_25fps", job.fileStem())
    }

    @Test fun hevc240Sections() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_hevc240.mp4")))
        // real time, then frames 240..480 at 30 fps (8× slower), 480..600 at 60, rest real time
        val segs = Segments.add(
            listOf(Segment(240, 480, Rational.of(30))), Segment(480, 600, Rational.of(60)),
        )
        val job = LosslessJob(info, Rational.of(25), segments = segs)
        val (_, out) = export(job, "hevc240_sections.mp4")
        assertEquals(960, out.frames.count)
        assertTiming(job, out)
        // 240/240 + 240/30 + 120/60 + 360/240 = 1 + 8 + 2 + 1.5 s
        assertEquals(Rational.parse("12.5"), job.outputDuration)
    }

    @Test fun avc120TrimmedKeepsRotation() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_avc120_rot.mp4")))
        val kf = info.frames.keyframes
        val job = LosslessJob(info, Rational.of(30), Trim(kf[1], kf[3]))
        val (_, out) = export(job, "avc120_trim.mp4")
        assertEquals(kf[3] - kf[1], out.frames.count)
        assertEquals(info.rotation, out.rotation)
        assertTiming(job, out)
    }

    @Test fun pixelSlowmoSections() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("PXL_20261025_152730266.mp4")))
        val job = LosslessJob(info, Rational.of(30), segments = listOf(Segment(300, 600, Rational.of(30))))
        val (_, out) = export(job, "pixel_sections.mp4")
        assertEquals(903, out.frames.count)
        assertTiming(job, out)
        File(outDir, "pixel_sections.mp4").delete()          // private footage: not pulled
    }

    private fun exportWithSound(job: LosslessJob, name: String): Pair<ClipInfo, Long> {
        val out = File(outDir, name)
        FileOutputStream(out).use { LosslessExport(ctx, job, withAudio = true).run(it.fd) }
        val info = Probe.probe(ctx, Uri.fromFile(out))
        assertEquals("AAC stereo 48 kHz", info.audio)
        return info to audioDurationUs(out)
    }

    /** End of the last audio sample (µs), from the muxed file. */
    private fun audioDurationUs(f: File): Long {
        val ex = android.media.MediaExtractor()
        ex.setDataSource(f.path)
        val t = (0 until ex.trackCount).first {
            ex.getTrackFormat(it).getString(android.media.MediaFormat.KEY_MIME)!!.startsWith("audio/")
        }
        val dur = ex.getTrackFormat(t).getLong(android.media.MediaFormat.KEY_DURATION)
        ex.release()
        return dur
    }

    @Test fun toneStretchedTo25() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_tone240.mp4")))
        val job = LosslessJob(info, Rational.of(25))                  // 9.6× slower, 38.4 s
        val (out, audioUs) = exportWithSound(job, "tone240_to25.mp4")
        assertEquals(38.4, out.durationUs / 1e6, 0.05)
        assertEquals(38.4, audioUs / 1e6, 0.05)
    }

    @Test fun toneSections() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_tone240.mp4")))
        // 0..240 real time (1 s), 240..480 at 30 fps (8 s), 480..960 real time (2 s)
        val job = LosslessJob(info, Rational.of(30), segments = listOf(Segment(240, 480, Rational.of(30))))
        val (_, audioUs) = exportWithSound(job, "tone240_sections.mp4")
        assertEquals(11.0, audioUs / 1e6, 0.05)
    }

    @Test fun slowmoSoundRestored() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_slowmo.mp4")))
        assertEquals(4.0, info.slowmoFactor!!, 1e-9)
        // real time: 240 frames at 120 fps = 2 s
        val job = LosslessJob(info, Rational.of(120))
        val (out, audioUs) = exportWithSound(job, "slowmo_realtime.mp4")
        assertEquals(2.0, out.durationUs / 1e6, 0.05)
        assertEquals(2.0, audioUs / 1e6, 0.05)
    }

    @Test fun pixelWithSound() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("PXL_20261025_152730266.mp4")))
        val job = LosslessJob(info, Rational.of(30), segments = listOf(Segment(300, 600, Rational.of(30))))
        val out = File(outDir, "pixel_sound.mp4")
        FileOutputStream(out).use { LosslessExport(ctx, job, withAudio = true).run(it.fd) }
        val audioUs = audioDurationUs(out)
        out.delete()                                          // private footage: not pulled
        assertEquals(job.outputDuration.toDouble(), audioUs / 1e6, 0.05)
    }

    @Test fun mediaStoreRoundTrip() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_avc120_rot.mp4")))
        val job = LosslessJob(info, Rational.of(30))
        val store = OutputStore(ctx)
        val out = store.create("vsc_device_test", "mp4", "video/mp4")
        try {
            store.open(out).use { LosslessExport(ctx, job).run(it.fileDescriptor) }
            store.publish(out)
            assertEquals(360, Probe.probe(ctx, out.uri).frames.count)
        } finally {
            store.discard(out)
        }
    }
}
