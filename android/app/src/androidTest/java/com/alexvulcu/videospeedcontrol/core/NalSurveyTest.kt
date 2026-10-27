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
            // length-prefixed NAL units (4 bytes)
            var p = 0
            val vcl = mutableListOf<String>()
            while (p + 6 <= size) {
                val len = buf.getInt(p)
                if (len <= 0 || p + 4 + len > size) break
                val b0 = buf.get(p + 4).toInt() and 0xff
                val b1 = buf.get(p + 5).toInt() and 0xff
                if (hevc) {
                    val type = (b0 shr 1) and 0x3f
                    val tid = (b1 and 7) - 1
                    if (type < 32) vcl += "t$type/L$tid"
                } else {
                    val type = b0 and 0x1f
                    val ref = (b0 shr 5) and 3
                    if (type in 1..5) vcl += "t$type/ref$ref"
                }
                p += 4 + len
            }
            val key = vcl.distinct().joinToString("+")
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
