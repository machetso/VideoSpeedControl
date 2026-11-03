package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import android.os.Handler
import android.os.HandlerThread
import java.io.FileDescriptor
import java.nio.ByteBuffer
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * Re-encode to a constant frame rate (desktop: `setpts=N/(rate)/TB` + `fps=`).
 * Decoder → SurfaceTexture → GPU (scale) → encoder input surface. Output frame k (time k/fps)
 * shows the last source frame that has started by then: a source frame is drawn once for every
 * output tick inside its own output interval – none if it is skipped (faster), several if it is
 * repeated (slower than the source). The sound comes from [Audio], as for lossless exports.
 *
 * Codecs run in asynchronous mode (callbacks on their own threads): polling them costs a
 * round trip to the media server per call (1–4 ms), which made the synchronous loop ~4× slower.
 * The GL work runs on the calling thread (the EGL context is bound to it); the muxer is only
 * touched on the encoder's callback thread.
 */
class ReencodeExport(
    private val context: Context,
    private val job: ReencodeJob,
    private val withAudio: Boolean = false,
) {
    @Volatile var cancelled = false

    private class Decoded(val index: Int, val ptsUs: Long, val size: Int, val eos: Boolean)

    /** Writes an MP4 to [fd]; [progress] gets 0..1. Returns the number of frames encoded. */
    fun run(fd: FileDescriptor, progress: (Float) -> Unit = {}): Int {
        val blockers = job.blockers()
        require(blockers.isEmpty()) { blockers.joinToString("; ") }
        val info = job.info
        val audioShare = if (withAudio && info.audio != null) 0.15f else 0f
        val audio = if (audioShare > 0) Audio.render(context, job, { cancelled }) { progress(it * audioShare) } else null
        val videoProgress = { p: Float -> progress(audioShare + p * (1 - audioShare)) }

        val pieces = job.pieces()
        val fps = job.fps
        val total = job.outputFrameCount
        val (w, h) = job.outputSize()
        val fm = info.frames
        val location = location(info)

        /** First output tick in the output interval of source frame [frame] (ceil of its time). */
        fun firstTick(frame: Int): Long {
            val t = Segments.outputTime(pieces, frame) * fps
            val k = t.floor()
            return if (Rational.of(k) == t) k else k + 1
        }

        val encFormat = MediaFormat.createVideoFormat(job.codec.mime, w, h).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, job.bitrate)
            setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR)
            setFloat(MediaFormat.KEY_FRAME_RATE, fps.toDouble().toFloat())
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
        }
        sourceVideoFormat(context, info)?.let { copyColorAspects(it, encFormat) }   // tagged like the source
        val encName = Encoders.pick(job.codec, encFormat, job.fastest)
            ?: error("No ${job.codec.label} encoder for ${w}×$h at ${fps.toDouble()} fps on this phone")

        val encThread = HandlerThread("vsc-encoder").apply { start() }
        val decThread = HandlerThread("vsc-decoder").apply { start() }
        val muxer = MediaMuxer(fd, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        val encoder = MediaCodec.createByCodecName(encName)
        val ex = Extractor()
        var decoder: MediaCodec? = null
        var gl: GlFrameGrabber? = null
        val decoded = LinkedBlockingQueue<Decoded>()
        val encoderDone = java.util.concurrent.CountDownLatch(1)
        val failureRef = java.util.concurrent.atomic.AtomicReference<Throwable?>(null)
        val muxStartedRef = java.util.concurrent.atomic.AtomicBoolean(false)
        val encodedCount = java.util.concurrent.atomic.AtomicInteger(0)

        // ---------------------------------------------------------------- encoder → muxer
        encoder.setCallback(object : MediaCodec.Callback() {
            private var videoTrack = -1
            private var audioTrack = -1
            private var nextAudio = 0
            private val abi = MediaCodec.BufferInfo()

            private fun writeAudioUntil(us: Long) {
                val a = audio ?: return
                while (nextAudio < a.samples.size && a.samples[nextAudio].ptsUs <= us) {
                    val s = a.samples[nextAudio++]
                    abi.set(0, s.data.size, s.ptsUs, s.flags)
                    muxer.writeSampleData(audioTrack, ByteBuffer.wrap(s.data), abi)
                }
            }

            override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {}   // surface input

            override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
                videoTrack = muxer.addTrack(format)
                audio?.let { audioTrack = muxer.addTrack(it.format) }
                location?.let { (lat, lon) -> muxer.setLocation(lat, lon) }
                muxer.start()
                muxStartedRef.set(true)
            }

            override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, bi: MediaCodec.BufferInfo) {
                try {
                    if (bi.size > 0 && bi.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0) {
                        val buf = codec.getOutputBuffer(index)!!
                        buf.position(bi.offset).limit(bi.offset + bi.size)
                        writeAudioUntil(bi.presentationTimeUs)
                        muxer.writeSampleData(videoTrack, buf, bi)
                        encodedCount.incrementAndGet()
                    }
                    codec.releaseOutputBuffer(index, false)
                    if (bi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) {
                        writeAudioUntil(Long.MAX_VALUE)
                        encoderDone.countDown()
                    }
                } catch (e: Throwable) {
                    failureRef.compareAndSet(null, e)
                    encoderDone.countDown()
                }
            }

            override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                failureRef.compareAndSet(null, e)
                encoderDone.countDown()
                decoded.offer(Decoded(-1, 0, 0, true))
            }
        }, Handler(encThread.looper))
        encoder.configure(encFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        val inputSurface = encoder.createInputSurface()
        encoder.start()

        try {
            val g = GlFrameGrabber(w, h, inputSurface)
            gl = g

            // ------------------------------------------------------------ extractor → decoder
            ex.setDataSource(context, info.uri, null)
            val track = (0 until ex.trackCount).first {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            }
            val inFormat = ex.getTrackFormat(track)
            ex.selectTrack(track)
            ex.seekTo(fm.ptsUs[job.trim.start], MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            val endUs = if (job.trimEnd < fm.count) fm.ptsUs[job.trimEnd] else Long.MAX_VALUE
            val dec = MediaCodec.createDecoderByType(inFormat.getString(MediaFormat.KEY_MIME)!!)
            decoder = dec
            dec.setCallback(object : MediaCodec.Callback() {
                private var inputDone = false

                override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
                    if (inputDone) return
                    try {
                        val n = ex.readSampleData(codec.getInputBuffer(index)!!, 0)
                        // stop feeding at the first keyframe after the trim end (complete GOPs before it)
                        val past = n >= 0 && ex.sampleTime >= endUs &&
                            ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0
                        if (n < 0 || past || cancelled) {
                            codec.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                            inputDone = true
                        } else {
                            codec.queueInputBuffer(index, 0, n, ex.sampleTime, 0)
                            ex.advance()
                        }
                    } catch (e: Throwable) {
                        failureRef.compareAndSet(null, e)
                        decoded.offer(Decoded(-1, 0, 0, true))
                    }
                }

                override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, bi: MediaCodec.BufferInfo) {
                    decoded.offer(Decoded(index, bi.presentationTimeUs, bi.size,
                        bi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0))
                }

                override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {}

                override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                    failureRef.compareAndSet(null, e)
                    decoded.offer(Decoded(-1, 0, 0, true))
                }
            }, Handler(decThread.looper))
            dec.configure(inFormat, g.surface, null, 0)
            dec.start()

            // ------------------------------------------------------------ decoded frames → GPU → encoder
            var nextTick = 0L
            while (nextTick < total) {
                if (cancelled) throw ExportCancelled()
                failureRef.get()?.let { throw it }
                val d = decoded.poll(5, TimeUnit.SECONDS) ?: error("The decoder stopped responding")
                failureRef.get()?.let { throw it }
                if (d.index < 0) break
                val f = if (d.size > 0) fm.indexOf(d.ptsUs) else -1
                val endTick = if (f >= 0 && f + 1 < job.trimEnd) minOf(firstTick(f + 1), total.toLong()) else total.toLong()
                val use = f >= job.trim.start && f < job.trimEnd && nextTick < endTick
                dec.releaseOutputBuffer(d.index, use)
                if (use && g.awaitFrame()) {
                    while (nextTick < endTick) {
                        g.present((Rational.of(nextTick) / fps * Rational.of(1_000_000_000)).floor())
                        nextTick++
                    }
                    videoProgress(nextTick.toFloat() / total)
                }
                if (d.eos || (f >= 0 && f + 1 >= job.trimEnd)) break
            }
            encoder.signalEndOfInputStream()
            if (!encoderDone.await(30, TimeUnit.SECONDS)) error("The encoder did not finish")
            failureRef.get()?.let { throw it }
            progress(1f)
            return encodedCount.get()
        } finally {
            decoder?.let { runCatching { it.stop() }; it.release() }
            runCatching { encoder.stop() }
            encoder.release()
            gl?.release()
            inputSurface.release()
            ex.release()
            decThread.quitSafely()
            encThread.quitSafely()
            try {
                if (muxStartedRef.get()) muxer.stop()
            } finally {
                muxer.release()
            }
        }
    }

    private fun location(info: ClipInfo): Pair<Float, Float>? {
        val r = android.media.MediaMetadataRetriever()
        return try {
            r.setDataSource(context, info.uri)
            val s = r.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_LOCATION) ?: return null
            val m = Regex("""([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)""").find(s) ?: return null
            m.groupValues[1].toFloat() to m.groupValues[2].toFloat()
        } catch (_: Exception) {
            null
        } finally {
            r.release()
        }
    }
}

/**
 * Encoder choice per codec (see [VideoCodec]); sets the complexity for AV1 in [format].
 * AV1 fast = hardware only: phones without an AV1 chip only have Android's software encoder
 * (Android 14+), many times slower – there AV1 fast is not offered and Easy uses HEVC / H.264.
 */
object Encoders {
    private val infos: Array<MediaCodecInfo> by lazy { MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos }
    private val supported = java.util.concurrent.ConcurrentHashMap<String, Boolean>()

    private fun candidates(mime: String, format: MediaFormat?): List<MediaCodecInfo> =
        infos.filter { info ->
            info.isEncoder && mime in info.supportedTypes &&
                (format == null || runCatching { info.getCapabilitiesForType(mime).isFormatSupported(format) }.getOrDefault(false))
        }

    private fun candidates(codec: VideoCodec, format: MediaFormat?): List<MediaCodecInfo> =
        candidates(codec.mime, format).filter { codec != VideoCodec.AV1_FAST || it.isHardwareAccelerated }

    /** The phone has an encoder for [codec] at all (the codec list only offers these). */
    fun available(codec: VideoCodec): Boolean = candidates(codec, null).isNotEmpty()

    /** An encoder for [codec] takes [width]×[height] at [fps] – checked before an export starts (cached). */
    fun supports(codec: VideoCodec, width: Int, height: Int, fps: Double): Boolean =
        supported.getOrPut("${codec.name} $width $height $fps") {
            candidates(codec, probeFormat(codec.mime, width, height, fps)).isNotEmpty()
        }

    /** The same for the source codec [mime] (smart export re-encodes parts in it; cached). */
    fun supports(mime: String, width: Int, height: Int, fps: Double): Boolean =
        supported.getOrPut("$mime $width $height $fps") {
            candidates(mime, probeFormat(mime, width, height, fps)).isNotEmpty()
        }

    private fun probeFormat(mime: String, width: Int, height: Int, fps: Double) =
        MediaFormat.createVideoFormat(mime, width, height).apply { setFloat(MediaFormat.KEY_FRAME_RATE, fps.toFloat()) }

    /** [fastest]: AV1 best (software) at its lowest complexity instead of the highest. */
    fun pick(codec: VideoCodec, format: MediaFormat, fastest: Boolean = false): String? {
        val all = candidates(codec, format)
        val info = when (codec) {
            VideoCodec.AV1_BEST -> all.firstOrNull { it.isSoftwareOnly } ?: all.firstOrNull()
            else -> all.firstOrNull()
        } ?: return null
        if (codec == VideoCodec.AV1_FAST || codec == VideoCodec.AV1_BEST) {
            info.getCapabilitiesForType(codec.mime).encoderCapabilities?.complexityRange?.let { range ->
                if (range.upper > range.lower) {
                    format.setInteger(MediaFormat.KEY_COMPLEXITY,
                        if (codec == VideoCodec.AV1_BEST && !fastest) range.upper else range.lower)
                }
            }
        }
        return info.name
    }
}
