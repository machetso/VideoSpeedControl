package com.alexvulcu.videospeedcontrol.core

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Technical check of files on the phone (no pictures leave it): tracks, timestamps, sync flags
 * and a full decode with the phone's decoder. Files: -e files /sdcard/Movies/…/a.mp4,/…/b.mp4
 * Results in logcat (tag VscDiag).
 */
@RunWith(AndroidJUnit4::class)
class DiagnoseDeviceTest {
    private fun log(s: String) = Log.i("VscDiag", s)

    @Test fun diagnose() {
        val arg = InstrumentationRegistry.getArguments().getString("files")
        assumeTrue("no -e files given", arg != null)
        for (path in arg!!.split(',')) diagnose(File(path))
    }

    private fun diagnose(f: File) {
        log("==== ${f.name}: ${f.length()} bytes")
        val ex = MediaExtractor()
        try {
            ex.setDataSource(f.path)
        } catch (e: Exception) {
            log("  cannot open: $e"); return
        }
        for (t in 0 until ex.trackCount) {
            val fmt = ex.getTrackFormat(t)
            val mime = fmt.getString(MediaFormat.KEY_MIME)
            log("  track $t: $mime dur=${if (fmt.containsKey(MediaFormat.KEY_DURATION)) fmt.getLong(MediaFormat.KEY_DURATION) else -1} " +
                "csd0=${fmt.containsKey("csd-0")} ${if (mime!!.startsWith("video")) "${fmt.getInteger(MediaFormat.KEY_WIDTH)}x${fmt.getInteger(MediaFormat.KEY_HEIGHT)}" else ""}")
        }
        for (t in 0 until ex.trackCount) {
            val fmt = ex.getTrackFormat(t)
            val mime = fmt.getString(MediaFormat.KEY_MIME)!!
            ex.unselectTrack((t + ex.trackCount - 1) % ex.trackCount)
            for (u in 0 until ex.trackCount) ex.unselectTrack(u)
            ex.selectTrack(t)
            ex.seekTo(0, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            var n = 0; var sync = 0; var back = 0; var dup = 0; var first = Long.MIN_VALUE; var last = Long.MIN_VALUE
            var maxGap = 0L; var minGap = Long.MAX_VALUE; var firstSync = -1; var bytes = 0L
            val gaps = ArrayList<Long>()
            while (ex.sampleTrackIndex >= 0) {
                val p = ex.sampleTime
                if (n == 0) first = p
                if ((ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC) != 0) { sync++; if (firstSync < 0) firstSync = n }
                if (last != Long.MIN_VALUE) {
                    val g = p - last
                    if (g < 0) back++ else if (g == 0L) dup++
                    if (g > maxGap) maxGap = g
                    if (g < minGap) minGap = g
                    if (gaps.size < 4000) gaps += g
                }
                bytes += ex.sampleSize
                last = p; n++
                ex.advance()
            }
            log("  track $t $mime: $n samples, $bytes bytes, sync=$sync (first sync at sample $firstSync), pts ${first}..${last} µs, " +
                "backwards=$back, duplicates=$dup, gap min=$minGap max=$maxGap µs")
            if (mime.startsWith("video")) {
                val hist = gaps.groupingBy { (it + 500) / 1000 }.eachCount().entries.sortedByDescending { it.value }.take(8)
                log("  video gap histogram (ms → count): ${hist.joinToString { "${it.key}→${it.value}" }}")
                decode(f, t, fmt, n)
            }
        }
        ex.release()
    }

    /** Feed every sample to the phone's decoder (decode order as stored) and count the output. */
    private fun decode(f: File, track: Int, fmt: MediaFormat, samples: Int) {
        val ex = MediaExtractor()
        ex.setDataSource(f.path)
        ex.selectTrack(track)
        val dec = MediaCodec.createDecoderByType(fmt.getString(MediaFormat.KEY_MIME)!!)
        var out = 0; var err: String? = null
        val t0 = System.nanoTime()
        try {
            dec.configure(fmt, null, null, 0)
            dec.start()
            val info = MediaCodec.BufferInfo()
            var inDone = false
            var idle = 0
            while (idle < 200) {
                if (!inDone) {
                    val i = dec.dequeueInputBuffer(2000)
                    if (i >= 0) {
                        val n = ex.readSampleData(dec.getInputBuffer(i)!!, 0)
                        if (n < 0) { dec.queueInputBuffer(i, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM); inDone = true }
                        else { dec.queueInputBuffer(i, 0, n, ex.sampleTime, ex.sampleFlags); ex.advance() }
                    }
                }
                val o = dec.dequeueOutputBuffer(info, 2000)
                if (o >= 0) {
                    idle = 0
                    if (info.size > 0 || info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM == 0) out++
                    dec.releaseOutputBuffer(o, false)
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                } else idle++
            }
        } catch (e: Exception) {
            err = e.toString()
        } finally {
            runCatching { dec.stop() }; dec.release(); ex.release()
        }
        log("  decode: $out of $samples frames out in ${"%.1f".format((System.nanoTime() - t0) / 1e9)} s" + (err?.let { ", ERROR $it" } ?: ""))
    }
}
