package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import kotlin.coroutines.coroutineContext

/**
 * Small JPEG of every frame for frame-accurate scrubbing and the play preview (desktop:
 * `workers.ProxyLoader`, 384×216). Built once per clip in display order; above [MAX_FRAMES] only
 * every n-th frame is kept and the nearest one is shown.
 */
class Proxy(val count: Int, val width: Int, val height: Int) {
    val step: Int = maxOf(1, (count + MAX_FRAMES - 1) / MAX_FRAMES)
    private val jpegs = arrayOfNulls<ByteArray>((count + step - 1) / step)

    @Volatile var ready = 0          // frames decoded so far (progress; JPEGs may lag a little)
        private set

    val complete get() = ready >= count
    val fraction get() = ready.toFloat() / maxOf(1, count)
    val bytes get() = jpegs.sumOf { it?.size ?: 0 }

    fun has(frame: Int) = jpegs.getOrNull(frame / step) != null

    /** The proxy picture for [frame] (nearest stored one), or null if not built yet. */
    fun bitmap(frame: Int): Bitmap? {
        val data = jpegs.getOrNull(frame / step) ?: return null
        return BitmapFactory.decodeByteArray(data, 0, data.size)
    }

    internal fun put(frame: Int, jpeg: ByteArray) {
        if (frame % step == 0) jpegs[frame / step] = jpeg
    }

    internal fun advance(to: Int) {
        ready = to
    }

    companion object {
        const val MAX_FRAMES = 12000
        const val LONG_SIDE = 480
        private const val QUALITY = 75

        /**
         * Decode every frame of [info] into a new [Proxy]; [onProgress] now and then.
         * Hardware decoder → GPU (scale, rotate, YUV → RGB, see [GlFrameGrabber]) → JPEG.
         * (MediaMetadataRetriever.getFramesAtIndex: ~35 fps; YUV → RGB in Kotlin: ~45 fps.)
         * Runs on one thread without suspending – the EGL context is bound to it.
         */
        suspend fun build(context: Context, info: ClipInfo, onProgress: (Proxy) -> Unit): Proxy =
            withContext(Dispatchers.Default) {
                val (w, h) = if (info.displayWidth >= info.displayHeight)
                    LONG_SIDE to LONG_SIDE * info.displayHeight / maxOf(1, info.displayWidth)
                else LONG_SIDE * info.displayWidth / maxOf(1, info.displayHeight) to LONG_SIDE
                val proxy = Proxy(info.frames.count, w, h)
                val ex = MediaExtractor()
                var codec: MediaCodec? = null
                val grabber = GlFrameGrabber(w, h)
                val jpegs = java.util.concurrent.Executors.newFixedThreadPool(3)
                try {
                    ex.setDataSource(context, info.uri, null)
                    val track = (0 until ex.trackCount).first {
                        ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
                    }
                    val format = ex.getTrackFormat(track)
                    ex.selectTrack(track)
                    val dec = MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME)!!)
                    codec = dec
                    dec.configure(format, grabber.surface, null, 0)
                    dec.start()
                    val bi = MediaCodec.BufferInfo()
                    var inputDone = false
                    var done = 0
                    var lastReport = 0L
                    while (done < proxy.count) {
                        coroutineContext.ensureActive()
                        while (!inputDone) {
                            val i = dec.dequeueInputBuffer(0)
                            if (i < 0) break
                            run {
                                val n = ex.readSampleData(dec.getInputBuffer(i)!!, 0)
                                if (n < 0) {
                                    dec.queueInputBuffer(i, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                    inputDone = true
                                } else {
                                    dec.queueInputBuffer(i, 0, n, ex.sampleTime, 0)
                                    ex.advance()
                                }
                            }
                        }
                        val o = dec.dequeueOutputBuffer(bi, 2_000)
                        if (o >= 0) {
                            val eos = bi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                            val frame = if (bi.size > 0) info.frames.indexOf(bi.presentationTimeUs) else -1
                            val wanted = frame >= 0 && frame % proxy.step == 0
                            dec.releaseOutputBuffer(o, wanted)
                            if (wanted && grabber.awaitFrame()) {
                                val copy = grabber.grab().copy(Bitmap.Config.ARGB_8888, false)
                                jpegs.submit {
                                    val o2 = ByteArrayOutputStream(32 * 1024)
                                    copy.compress(Bitmap.CompressFormat.JPEG, QUALITY, o2)
                                    copy.recycle()
                                    proxy.put(frame, o2.toByteArray())
                                }
                            }
                            if (bi.size > 0) done++
                            val now = System.nanoTime()
                            if (now - lastReport > 100_000_000L || done >= proxy.count || eos) {
                                proxy.advance(done)
                                onProgress(proxy)
                                lastReport = now
                            }
                            if (eos) break
                        }
                    }
                    jpegs.shutdown()
                    jpegs.awaitTermination(30, java.util.concurrent.TimeUnit.SECONDS)
                    proxy.advance(proxy.count)
                    onProgress(proxy)
                } finally {
                    jpegs.shutdownNow()
                    codec?.let { runCatching { it.stop() }; it.release() }
                    grabber.release()
                    ex.release()
                }
                proxy
            }
    }
}
