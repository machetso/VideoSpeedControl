package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream

/**
 * "Convert videos" with an old-style AVI (user request 2026-11-03): Android's own extractor can't
 * read AVI, [Extractor] falls back to Media3. Synthetic clip like the user's DivX cartoons –
 * make it with the desktop FFmpeg (see the tools/device_test.sh call in CLAUDE.md):
 *   ffmpeg -f lavfi -i testsrc2=s=368x208:r=10:d=20 -f lavfi -i sine=f=440:d=20:sample_rate=22050
 *     -c:v mpeg4 -vtag XVID -q:v 4 -c:a libmp3lame -ac 2 -b:a 96k -shortest synth_divx.avi
 * Output stays in cache/out/ for a check with the desktop's ffprobe.
 */
@RunWith(AndroidJUnit4::class)
class ConvertDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val outDir = File(ctx.cacheDir, "out").apply { mkdirs() }

    @Test fun aviIsReadThroughMedia3() {
        val uri = Uri.fromFile(TestClips.get("synth_divx.avi"))
        val ex = Extractor()
        ex.setDataSource(ctx, uri, null)
        assertTrue("Android's extractor should refuse AVI", ex.usesMedia3)
        ex.release()
        val info = Probe.probe(ctx, uri)
        val p = info.frames.ptsUs
        Log.i("ConvertDeviceTest", "pts ${p.take(4)} … ${p.takeLast(3)} duration ${info.durationUs} keys ${info.frames.keyframes.take(5)}")
        assertEquals("video/mp4v-es", info.videoMime)
        assertEquals(368 to 208, info.width to info.height)
        assertEquals(Rational.of(10), info.fps)
        assertEquals(200, info.frames.count)
        assertTrue(info.audio, info.audio!!.startsWith("MP3"))
    }

    /**
     * The same AVI through a content:// link (folder picker / MediaStore). Media3 found the tracks
     * of the user's DivX files that way but read no frames (2026-11-04) – [Extractor] now hands it
     * an open file. Needs an AVI in the phone's video library; skipped when there is none.
     */
    @Test fun aviThroughContentLink() {
        InstrumentationRegistry.getInstrumentation().uiAutomation
            .grantRuntimePermission(ctx.packageName, "android.permission.READ_MEDIA_VIDEO")
        val coll = android.provider.MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        val uri = ctx.contentResolver.query(coll, arrayOf("_id"), "_display_name LIKE ?", arrayOf("%.avi"), null)
            ?.use { c -> if (c.moveToFirst()) android.content.ContentUris.withAppendedId(coll, c.getLong(0)) else null }
        assumeTrue("no AVI in the phone's video library", uri != null)
        val info = Probe.probe(ctx, uri!!)
        Log.i("ConvertDeviceTest", "content link: ${info.name} ${info.frames.count} frames")
        assertTrue(info.frames.count > 0)
        assertTrue(info.durationUs > 0)
    }

    @Test fun convertAviToAv1WithSound() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_divx.avi")))
        val job = Convert.job(info, VideoCodec.AV1_FAST, Quality.HIGH)
        Log.i("ConvertDeviceTest", "codec ${job.codec} fastest ${job.fastest} bitrate ${job.bitrate}")
        assertTrue(job.codec == VideoCodec.AV1_FAST || job.codec == VideoCodec.AV1_BEST)
        val out = File(outDir, "convert_divx_av1.mp4")
        val t0 = System.nanoTime()
        val n = FileOutputStream(out).use { ReencodeExport(ctx, job, withAudio = true).run(it.fd) }
        val seconds = (System.nanoTime() - t0) / 1e9
        Log.i("ConvertDeviceTest", "200 frames in %.2f s (%.0f fps), %d bytes".format(seconds, 200 / seconds, out.length()))
        assertEquals(200, n)
        val o = Probe.probe(ctx, Uri.fromFile(out))
        assertEquals("video/av01", o.videoMime)
        assertEquals(368 to 208, o.width to o.height)
        assertEquals(Rational.of(10), o.fps)
        assertEquals(200, o.frames.count)
        assertNotNull(o.audio)
        assertTrue(o.audio, o.audio!!.startsWith("AAC"))
        assertEquals(20.0, o.durationUs / 1e6, 0.15)
        assertEquals("synth_divx", Convert.cleanStem(info.name))
    }

    @Test fun convertAviToHevc() {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_divx.avi")))
        val job = Convert.job(info, VideoCodec.HEVC, Quality.GOOD)
        val out = File(outDir, "convert_divx_hevc.mp4")
        val n = FileOutputStream(out).use { ReencodeExport(ctx, job, withAudio = true).run(it.fd) }
        assertEquals(200, n)
        val o = Probe.probe(ctx, Uri.fromFile(out))
        assertEquals(368 to 208, o.width to o.height)
        assertEquals(200, o.frames.count)
    }
}
