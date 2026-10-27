package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.Closeable

/**
 * Pictures of one clip: keyframe thumbnails (timeline strip + instant scrubbing) and exact
 * frames for the playhead. MediaMetadataRetriever is not thread-safe – one per job, each behind
 * a mutex. The returned frames are already rotated for display.
 */
class FrameSource(context: Context, private val info: ClipInfo) : Closeable {
    private val exact = MediaMetadataRetriever().apply { setDataSource(context, info.uri) }
    private val thumbs = MediaMetadataRetriever().apply { setDataSource(context, info.uri) }
    private val exactLock = Mutex()
    private val thumbLock = Mutex()

    /** Thumbnails of up to [max] keyframes spread over the clip: (frame index, picture). */
    suspend fun thumbnails(max: Int, width: Int, onEach: (Int, Bitmap) -> Unit) = withContext(Dispatchers.IO) {
        val keys = info.frames.keyframes
        val pick = if (keys.size <= max) keys.toList()
        else (0 until max).map { keys[(it.toLong() * (keys.size - 1) / (max - 1)).toInt()] }.distinct()
        val height = width * info.displayHeight / maxOf(1, info.displayWidth)
        for (k in pick) {
            val bmp = thumbLock.withLock {
                thumbs.getScaledFrameAtTime(info.frames.ptsUs[k], MediaMetadataRetriever.OPTION_CLOSEST_SYNC, width, height)
            } ?: continue
            onEach(k, bmp)
        }
    }

    /** The exact frame [index], fitted into [width] × [width] (aspect kept). */
    suspend fun frame(index: Int, width: Int): Bitmap? = withContext(Dispatchers.IO) {
        val us = info.frames.ptsUs[index.coerceIn(0, info.frames.count - 1)]
        val height = width * info.displayHeight / maxOf(1, info.displayWidth)
        exactLock.withLock {
            exact.getScaledFrameAtTime(us, MediaMetadataRetriever.OPTION_CLOSEST, width, height)
        }
    }

    /** Releases the retrievers once running requests are done. */
    suspend fun release() = withContext(Dispatchers.IO) {
        exactLock.withLock { runCatching { exact.release() } }
        thumbLock.withLock { runCatching { thumbs.release() } }
    }

    override fun close() {
        runCatching { exact.release() }
        runCatching { thumbs.release() }
    }
}
