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
 * `workers.ProxyLoader`, 384×216). Built in display order; above [MAX_FRAMES] only every n-th
 * frame is kept and the nearest one is shown. Kept in [chunks] from keyframe to keyframe, which
 * [PreviewCache] stores (0.93): a video opened again loads them and decodes only what is missing.
 */
class Proxy(val count: Int, val width: Int, val height: Int, keyframes: IntArray = intArrayOf(0)) {
    val step: Int = maxOf(1, (count + MAX_FRAMES - 1) / MAX_FRAMES)
    private val jpegs = arrayOfNulls<ByteArray>((count + step - 1) / step)

    /** Frame ranges from one keyframe to the next (the unit that is stored and rebuilt). */
    val chunks: List<IntRange> = run {
        val starts = (listOf(0) + keyframes.filter { it in 1 until count }).distinct().sorted()
        starts.mapIndexed { i, a -> a until (starts.getOrNull(i + 1) ?: count) }
    }
    private val chunkMissing = IntArray(chunks.size) { i -> chunks[i].count { it % step == 0 } }
    /** Called (from a JPEG thread) when a chunk has all its pictures – the cache writes it. */
    @Volatile var onChunkComplete: ((Int) -> Unit)? = null

    @Volatile var ready = 0          // frames done so far (loaded or decoded; progress)
        private set

    val complete get() = ready >= count
    val fraction get() = ready.toFloat() / maxOf(1, count)
    val bytes get() = jpegs.sumOf { it?.size ?: 0 }

    fun has(frame: Int) = jpegs.getOrNull(frame / step) != null

    /** The stored JPEG of [frame] (a frame this proxy keeps), or null. */
    fun jpeg(frame: Int): ByteArray? = if (frame % step == 0) jpegs.getOrNull(frame / step) else null

    /** The proxy picture for [frame] (nearest stored one), or null if not built yet. */
    fun bitmap(frame: Int): Bitmap? {
        val data = jpegs.getOrNull(frame / step) ?: return null
        return BitmapFactory.decodeByteArray(data, 0, data.size)
    }

    fun chunkOf(frame: Int): Int {
        var lo = 0; var hi = chunks.size - 1
        while (lo < hi) { val mid = (lo + hi + 1) / 2; if (chunks[mid].first <= frame) lo = mid else hi = mid - 1 }
        return lo
    }

    internal fun put(frame: Int, jpeg: ByteArray) {
        if (frame % step != 0) return
        val first = synchronized(this) {
            val was = jpegs[frame / step] == null
            jpegs[frame / step] = jpeg
            if (was) { val c = chunkOf(frame); chunkMissing[c]--; if (chunkMissing[c] == 0) c else -1 } else -1
        }
        if (first >= 0) onChunkComplete?.invoke(first)
    }

    internal fun advance(to: Int) {
        ready = to
    }

    companion object {
        const val MAX_FRAMES = 12000
        const val LONG_SIDE = 480
        /** JPEG 60: 17 KB and 1.1 ms per 480×270 picture on the Pixel (75: 22 KB, 2.3 ms; WebP: 13 KB, 13.7 ms). */
        const val QUALITY = 60

        fun sizeFor(info: ClipInfo): Pair<Int, Int> = if (info.displayWidth >= info.displayHeight)
            LONG_SIDE to LONG_SIDE * info.displayHeight / maxOf(1, info.displayWidth)
        else LONG_SIDE * info.displayWidth / maxOf(1, info.displayHeight) to LONG_SIDE

        /**
         * The proxy of [info]: chunks stored in [cache] under [fingerprint] are loaded, the others
         * decoded (from their keyframe) and stored as soon as each is complete. [onProgress] now and
         * then. Hardware decoder → GPU (scale, rotate, YUV → RGB, see [GlFrameGrabber]) → JPEG.
         * Runs on one thread without suspending – the EGL context is bound to it.
         */
        suspend fun build(context: Context, info: ClipInfo, cache: PreviewCache? = null, fingerprint: String? = null,
                          onProgress: (Proxy) -> Unit): Proxy =
            withContext(Dispatchers.Default) {
                val (w, h) = sizeFor(info)
                val proxy = Proxy(info.frames.count, w, h, info.frames.keyframes)
                val loaded = if (cache != null && fingerprint != null) cache.loadChunks(fingerprint, proxy) else emptySet()
                var done = loaded.sumOf { proxy.chunks[it].count() }
                proxy.advance(done)
                onProgress(proxy)
                if (cache != null && fingerprint != null) {
                    proxy.onChunkComplete = { i -> runCatching { cache.writeChunk(fingerprint, proxy, i) } }
                }
                // runs of chunks still to decode
                val runs = mutableListOf<IntRange>()
                for ((i, c) in proxy.chunks.withIndex()) {
                    if (i in loaded) continue
                    val last = runs.lastOrNull()
                    runs += if (last != null && last.last + 1 == c.first) { runs.removeAt(runs.lastIndex); last.first..c.last } else c
                }
                if (runs.isEmpty()) {
                    proxy.advance(proxy.count)
                    onProgress(proxy)
                    return@withContext proxy
                }
                val ex = Extractor()
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
                    var lastReport = 0L
                    for ((r, run) in runs.withIndex()) {
                        if (r > 0) dec.flush()
                        // every chunk starts at a keyframe – decoding starts exactly there
                        ex.seekTo(info.frames.ptsUs[run.first], MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
                        var inputDone = false
                        var got = 0
                        val need = run.count()
                        while (got < need) {
                            coroutineContext.ensureActive()
                            while (!inputDone) {
                                val i = dec.dequeueInputBuffer(0)
                                if (i < 0) break
                                val n = ex.readSampleData(dec.getInputBuffer(i)!!, 0)
                                if (n < 0) {
                                    dec.queueInputBuffer(i, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                    inputDone = true
                                } else {
                                    dec.queueInputBuffer(i, 0, n, ex.sampleTime, 0)
                                    ex.advance()
                                }
                            }
                            val o = dec.dequeueOutputBuffer(bi, 2_000)
                            if (o >= 0) {
                                val eos = bi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                                val frame = if (bi.size > 0) info.frames.indexOf(bi.presentationTimeUs) else -1
                                val inRun = frame in run              // leading pictures of a seek belong elsewhere
                                val wanted = inRun && frame % proxy.step == 0
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
                                if (inRun) { got++; done++ }
                                val now = System.nanoTime()
                                if (now - lastReport > 100_000_000L) {
                                    proxy.advance(minOf(done, proxy.count - 1))
                                    onProgress(proxy)
                                    lastReport = now
                                }
                                if (eos) break
                            }
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
