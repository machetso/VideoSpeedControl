package com.alexvulcu.videospeedcontrol.core

import android.media.MediaExtractor
import android.media.MediaFormat
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith

/** Logs the colour description of clips and of what the encoder writes (tag VscColor). */
@RunWith(AndroidJUnit4::class)
class ColorInfoDeviceTest {
    private fun keys(f: MediaFormat) = listOf(MediaFormat.KEY_COLOR_STANDARD, MediaFormat.KEY_COLOR_RANGE,
        MediaFormat.KEY_COLOR_TRANSFER).joinToString { k -> "$k=" + (if (f.containsKey(k)) f.getInteger(k) else "-") }

    private fun log(name: String, path: String) {
        val ex = MediaExtractor()
        ex.setDataSource(path)
        val f = (0 until ex.trackCount).map { ex.getTrackFormat(it) }.first { it.getString(MediaFormat.KEY_MIME)!!.startsWith("video/") }
        Log.i("VscColor", "$name: ${f.getString(MediaFormat.KEY_MIME)} ${keys(f)}")
        ex.release()
    }

    @Test fun clips() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        log("pixel120", TestClips.get("PXL_20261025_152730266.mp4").path)
        val ex = MediaExtractor()
        // the user's test clip in Movies (read in place, metadata only)
        val uri = android.provider.MediaStore.Video.Media.getContentUri(android.provider.MediaStore.VOLUME_EXTERNAL_PRIMARY)
        ctx.contentResolver.query(uri, arrayOf(android.provider.MediaStore.Video.Media._ID),
            "${android.provider.MediaStore.Video.Media.DISPLAY_NAME} = ?", arrayOf("PXL_SloMoTest.mp4"), null)?.use { c ->
            if (c.moveToFirst()) {
                runCatching {
                    ex.setDataSource(ctx, android.content.ContentUris.withAppendedId(uri, c.getLong(0)), null)
                    val f = (0 until ex.trackCount).map { ex.getTrackFormat(it) }.first { it.getString(MediaFormat.KEY_MIME)!!.startsWith("video/") }
                    Log.i("VscColor", "PXL_SloMoTest: ${keys(f)}")
                }.onFailure { Log.i("VscColor", "PXL_SloMoTest not readable: $it") }
            }
        }
        ex.release()
        val out = java.io.File(ctx.cacheDir, "out/smart_pixel.mp4")
        if (out.isFile) log("smart_pixel (track format)", out.path)
    }
}
