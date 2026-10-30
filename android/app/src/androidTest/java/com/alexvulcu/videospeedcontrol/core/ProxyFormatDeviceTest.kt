package com.alexvulcu.videospeedcontrol.core

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

/** Size and speed of proxy picture formats on this phone (real frames, 480 px long side). */
@RunWith(AndroidJUnit4::class)
class ProxyFormatDeviceTest {
    @Test fun compareFormats() {
        val clip = File("/data/local/tmp/vsc/PXL_20261025_152730266.mp4")
        assumeTrue(clip.exists())
        val local = TestClips.get(clip.name)
        val mmr = MediaMetadataRetriever().apply { setDataSource(local.path) }
        val n = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_FRAME_COUNT)!!.toInt()
        val frames = (0 until 40).map { i ->
            val b = mmr.getFrameAtIndex(i * (n - 1) / 39)!!
            val (w, h) = if (b.width >= b.height) 480 to 480 * b.height / b.width else 480 * b.width / b.height to 480
            Bitmap.createScaledBitmap(b, w, h, true).also { b.recycle() }
        }
        mmr.release()
        @Suppress("DEPRECATION")
        val formats = listOf(
            Triple("JPEG q75", Bitmap.CompressFormat.JPEG, 75),
            Triple("JPEG q60", Bitmap.CompressFormat.JPEG, 60),
            Triple("WebP lossy q75", Bitmap.CompressFormat.WEBP_LOSSY, 75),
            Triple("WebP lossy q60", Bitmap.CompressFormat.WEBP_LOSSY, 60),
            Triple("WebP lossy q40", Bitmap.CompressFormat.WEBP_LOSSY, 40),
        )
        for ((name, fmt, q) in formats) {
            repeat(2) { frames[0].compress(fmt, q, ByteArrayOutputStream()) }      // warm-up
            var bytes = 0L
            val data = ArrayList<ByteArray>()
            var t0 = System.nanoTime()
            for (f in frames) { val o = ByteArrayOutputStream(); f.compress(fmt, q, o); bytes += o.size(); data += o.toByteArray() }
            val enc = (System.nanoTime() - t0) / 1e6 / frames.size
            t0 = System.nanoTime()
            for (d in data) BitmapFactory.decodeByteArray(d, 0, d.size).recycle()
            val dec = (System.nanoTime() - t0) / 1e6 / frames.size
            Log.i("VscFormat", "%-15s %6.1f KB/frame  encode %5.1f ms  decode %5.1f ms  (%dx%d)".format(
                name, bytes / 1024.0 / frames.size, enc, dec, frames[0].width, frames[0].height))
        }
    }
}
