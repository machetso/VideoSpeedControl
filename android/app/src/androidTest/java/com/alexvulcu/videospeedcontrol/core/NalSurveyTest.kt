package com.alexvulcu.videospeedcontrol.core

import android.media.MediaExtractor
import android.media.MediaFormat
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith
import java.nio.ByteBuffer

/**
 * Survey of the HEVC / H.264 frame structure of a clip (logcat tag VscNal): NAL unit types,
 * temporal layer ids, and the pattern over the first frames – which frames nothing depends on.
 */
@RunWith(AndroidJUnit4::class)
class NalSurveyTest {
    private fun survey(name: String) {
        val f = TestClips.get(name)
        val ex = MediaExtractor()
        ex.setDataSource(f.path)
        val t = (0 until ex.trackCount).first { ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)!!.startsWith("video/") }
        val mime = ex.getTrackFormat(t).getString(MediaFormat.KEY_MIME)!!
        val hevc = mime == MediaFormat.MIMETYPE_VIDEO_HEVC
        ex.selectTrack(t)
        val buf = ByteBuffer.allocateDirect(16 shl 20)
        val types = sortedMapOf<String, Int>()
        val pattern = StringBuilder()
        var n = 0
        while (true) {
            val size = ex.readSampleData(buf, 0)
            if (size < 0) break
            // MediaExtractor hands out Annex-B (start codes) – Smart.nalTypes reads both layouts
            val vcl = (Smart.nalTypes(buf, size, hevc) ?: emptyList()).map { "t$it" }
            val key = vcl.distinct().joinToString("+")
            if (n < 3) Log.i("VscNal", "sample $n starts with " + (0 until 8).joinToString(" ") { "%02x".format(buf.get(it)) })
            types[key] = (types[key] ?: 0) + 1
            if (n < 64) pattern.append(key).append(' ')
            n++
            ex.advance()
        }
        ex.release()
        Log.i("VscNal", "$name ($mime): $n samples; types: $types")
        Log.i("VscNal", "$name first 64 (decode order): $pattern")
    }

    @Test fun pixel120() = survey("PXL_20261025_152730266.mp4")
}
