package com.alexvulcu.videospeedcontrol.core

import android.media.MediaFormat
import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.RandomAccessFile

/**
 * Convert videos, pro mode (2026-11-04): every container / sound combination written for real.
 * synth_divx.avi = 20 s, 368×208, 10 fps, MPEG-4 part 2 + MP3 22.05 kHz stereo (see
 * ConvertDeviceTest). Outputs stay in cache/out/pro_* for a check with the desktop's FFmpeg.
 */
@RunWith(AndroidJUnit4::class)
class ConvertProDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val outDir = File(ctx.cacheDir, "out").apply { mkdirs() }
    private val info by lazy { Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_divx.avi"))) }

    private fun convert(name: String, s: Convert.Settings): ClipInfo {
        val plan = Convert.plan(info, s)
        val out = File(outDir, "pro_$name.${plan.container.extension}")
        out.delete()
        val t0 = System.nanoTime()
        val n = RandomAccessFile(out, "rw").use { raf ->
            ReencodeExport(ctx, plan.job, plan.sound, plan.container, plan.audio).run(raf.fd)
        }
        Log.i("ConvertPro", "$name: $n frames, ${out.length()} bytes, %.1f s".format((System.nanoTime() - t0) / 1e9))
        return Probe.probe(ctx, Uri.fromFile(out))
    }

    @Test fun mkvAv1Mp3Copied() {
        val o = convert("av1_copy", Convert.Settings(container = OutMuxer.Container.MKV, audio = "copy"))
        assertEquals(MediaFormat.MIMETYPE_VIDEO_AV1, o.videoMime)
        assertEquals(368 to 208, o.width to o.height)
        assertEquals(200, o.frames.count)
        assertEquals(MediaFormat.MIMETYPE_AUDIO_MPEG, o.audioMime)
        assertEquals(22050, o.audioRate)
    }

    @Test fun mkvHevcAacMono() {
        val o = convert("hevc_aac_mono", Convert.Settings(codec = VideoCodec.HEVC, container = OutMuxer.Container.MKV,
            rate = Convert.Rate.KBPS, kbps = 400, audio = "aac", channels = 1, audioKbps = 64))
        assertEquals(MediaFormat.MIMETYPE_VIDEO_HEVC, o.videoMime)
        assertEquals(200, o.frames.count)
        assertEquals(MediaFormat.MIMETYPE_AUDIO_AAC, o.audioMime)
        assertEquals(1, o.audioChannels)
        assertEquals(22050, o.audioRate)
    }

    @Test fun mkvAvcOpus25fps() {
        val o = convert("avc_opus_25", Convert.Settings(codec = VideoCodec.AVC, container = OutMuxer.Container.MKV,
            fps = Rational.of(25), audio = "opus", audioKbps = 64))
        assertEquals(MediaFormat.MIMETYPE_VIDEO_AVC, o.videoMime)
        assertEquals(500, o.frames.count)                       // 20 s at 25 fps
        assertEquals(MediaFormat.MIMETYPE_AUDIO_OPUS, o.audioMime)
        assertEquals(20.0, o.durationUs / 1e6, 0.2)
    }

    @Test fun mkvAv1Flac() {
        val o = convert("av1_flac", Convert.Settings(container = OutMuxer.Container.MKV, audio = "flac"))
        assertEquals(MediaFormat.MIMETYPE_AUDIO_FLAC, o.audioMime)
        assertEquals(200, o.frames.count)
    }

    @Test fun mp4RefusesOpusAndMp3() {        // MediaMuxer refuses both (tested 2026-11-04)
        assertTrue(Convert.audioProblem(info, Convert.Settings(audio = "opus")) != null)
        assertTrue(Convert.audioProblem(info, Convert.Settings(audio = "copy")) != null)
        assertEquals(null, Convert.audioProblem(info, Convert.Settings(audio = "copy", container = OutMuxer.Container.MKV)))
    }

    @Test fun bitratesMeasured() {           // AVI / MP3: Android states no data rates
        Log.i("ConvertPro", "video ${info.videoBitrate} audio ${info.audioBitrate}")
        assertEquals(96_000.0, info.audioBitrate!!.toDouble(), 3000.0)
        assertTrue(info.videoBitrate!! in 100_000..2_000_000)
    }

    @Test fun movAac() {
        val o = convert("mov_aac", Convert.Settings(codec = VideoCodec.HEVC, container = OutMuxer.Container.MOV, audio = "aac"))
        assertEquals(MediaFormat.MIMETYPE_AUDIO_AAC, o.audioMime)
        assertEquals(22050, o.audioRate)
        assertTrue(o.frames.count == 200)
    }

    @Test fun smartRules() {
        val s = Convert.suggest(info, VideoCodec.AV1_FAST, Convert.Goal.IDENTICAL, OutMuxer.Container.MP4)
        Log.i("ConvertPro", "smart: $s (source video ${info.videoBitrate}, audio ${info.audioMime} ${info.audioBitrate})")
        assertEquals("aac", s.audio)                            // MP3 can't go into MP4 on the phone
        val k = Convert.suggest(info, VideoCodec.AV1_FAST, Convert.Goal.IDENTICAL, OutMuxer.Container.MKV)
        assertEquals("copy", k.audio)
    }
}
