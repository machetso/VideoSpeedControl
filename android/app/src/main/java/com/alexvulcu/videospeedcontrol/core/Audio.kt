package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaExtractor
import android.media.MediaFormat
import androidx.annotation.OptIn
import androidx.media3.common.audio.AudioProcessor
import androidx.media3.common.audio.SonicAudioProcessor
import androidx.media3.common.util.UnstableApi
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.roundToLong

/**
 * Sound: stretched or compressed to the new video length, the pitch stays the same.
 * Port of `vsc/core/audio.py`:
 * 1. Phone slow motion stores its sound slowed down like a tape; reading the samples at
 *    rate × slow-mo factor brings back the original pitch and real-time length (`asetrate`).
 * 2. Every run of frames with one speed (whole trim, or each section) gets its piece of sound
 *    time-stretched with pitch preserved (Sonic here, rubberband on the desktop).
 * 3. Each piece is cut / padded to its exact output length (the desktop only fixes the total),
 *    so the sound stays in sync at every section border.
 * The result is AAC, kept in memory (192 kbit/s ≈ 1.4 MB per minute) and muxed with the video.
 */
object Audio {
    const val OUT_RATE = 48000
    const val BITRATE = 192_000
    private const val AAC_FRAME = 1024L

    /** (start, end, output length) in seconds of real-time sound per run of one speed. */
    data class Span(val start: Double, val end: Double, val out: Double)

    class Encoded(val format: MediaFormat, val samples: List<Sample>) {
        class Sample(val data: ByteArray, val ptsUs: Long, val flags: Int)
    }

    fun slowmoFactor(info: ClipInfo): Double = (info.realFps / info.fps).toDouble()

    /** Start of source frame [frame] on the file's timeline in seconds (end of clip for count). */
    private fun fileTime(info: ClipInfo, frame: Int): Double {
        val p = info.frames.ptsUs
        if (frame < p.size) return p[frame] / 1e6
        val last = if (p.size > 1) p[p.size - 1] - p[p.size - 2] else (1e6 / info.fps.toDouble()).toLong()
        return (p.last() + last) / 1e6
    }

    fun spans(job: Timing): List<Span> {
        val k = slowmoFactor(job.info)
        if (!job.hasSegments) {
            return listOf(Span(fileTime(job.info, job.trim.start) / k, fileTime(job.info, job.trimEnd) / k,
                job.outputDuration.toDouble()))
        }
        return job.pieces().map { p ->
            Span(fileTime(job.info, p.start) / k, fileTime(job.info, p.end) / k,
                (Rational.of((p.end - p.start).toLong()) / p.rate).toDouble())
        }
    }

    /** Decode, restore, stretch and encode the sound for [job]. [progress] gets 0..1. */
    @OptIn(UnstableApi::class)
    fun render(context: Context, job: Timing, isCancelled: () -> Boolean, progress: (Float) -> Unit): Encoded? {
        val info = job.info
        val ex = MediaExtractor()
        ex.setDataSource(context, info.uri, null)
        try {
            val track = (0 until ex.trackCount).firstOrNull {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: return null
            val inFormat = ex.getTrackFormat(track)
            val k = slowmoFactor(info)
            val spans = spans(job)
            ex.selectTrack(track)
            // seek a little before the first span (the decoder needs to warm up)
            ex.seekTo(maxOf(0L, ((spans.first().start * k - 0.5) * 1e6).toLong()), MediaExtractor.SEEK_TO_PREVIOUS_SYNC)

            // asynchronous decoder: polling a codec costs a media-server round trip per call
            val thread = android.os.HandlerThread("vsc-audio-dec").apply { start() }
            val outputs = java.util.concurrent.LinkedBlockingQueue<Pair<Int, MediaCodec.BufferInfo>>()
            val failure = java.util.concurrent.atomic.AtomicReference<Throwable?>(null)
            val lastSpanEnd = spans.last().end
            val decoder = MediaCodec.createDecoderByType(inFormat.getString(MediaFormat.KEY_MIME)!!)
            inFormat.setInteger(MediaFormat.KEY_PCM_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
            decoder.setCallback(object : MediaCodec.Callback() {
                private var inputDone = false
                override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
                    if (inputDone) return
                    try {
                        val n = ex.readSampleData(codec.getInputBuffer(index)!!, 0)
                        if (n < 0 || ex.sampleTime / 1e6 / k > lastSpanEnd + 0.5) {
                            codec.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                            inputDone = true
                        } else {
                            codec.queueInputBuffer(index, 0, n, ex.sampleTime, 0)
                            ex.advance()
                        }
                    } catch (e: Throwable) {
                        failure.compareAndSet(null, e)
                        outputs.offer(-1 to MediaCodec.BufferInfo())
                    }
                }
                override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo) {
                    outputs.offer(index to MediaCodec.BufferInfo().apply { set(info.offset, info.size, info.presentationTimeUs, info.flags) })
                }
                override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {}
                override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                    failure.compareAndSet(null, e)
                    outputs.offer(-1 to MediaCodec.BufferInfo())
                }
            }, android.os.Handler(thread.looper))
            decoder.configure(inFormat, null, null, 0)
            val stretch = Stretcher(spans, k)
            val encoder = AacEncoder()
            decoder.start()
            try {
                val total = spans.last().end - spans.first().start
                while (true) {
                    if (isCancelled()) throw ExportCancelled()
                    val (o, bi) = outputs.poll(5, java.util.concurrent.TimeUnit.SECONDS)
                        ?: error("The audio decoder stopped responding")
                    failure.get()?.let { throw it }
                    if (o < 0) break
                    if (bi.size > 0) {
                        val fmt = decoder.getOutputFormat(o)
                        val buf = decoder.getOutputBuffer(o)!!
                        buf.position(bi.offset).limit(bi.offset + bi.size)
                        stretch.feed(buf, bi.presentationTimeUs, fmt, encoder)
                        progress(((stretch.position - spans.first().start) / total).toFloat().coerceIn(0f, 1f))
                    }
                    decoder.releaseOutputBuffer(o, false)
                    if (bi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0 || stretch.finished) break
                }
                stretch.finish(encoder)
                progress(1f)
                return encoder.finish()
            } finally {
                runCatching { decoder.stop() }
                decoder.release()
                encoder.release()
                thread.quitSafely()
            }
        } finally {
            ex.release()
        }
    }

    /**
     * Cuts the decoded sound into spans and time-stretches each one; output is 48 kHz stereo
     * (or mono) 16-bit PCM handed to the encoder, each span exactly as long as its video piece.
     */
    @OptIn(UnstableApi::class)
    private class Stretcher(val spans: List<Span>, val k: Double) {
        var finished = false
        var position = spans.first().start        // real-time seconds reached in the input
        private var span = 0
        private var sonic: SonicAudioProcessor? = null
        private var inRate = 0
        private var inChannels = 0
        private var outChannels = 0
        private var written = 0L                  // output frames so far (all spans)
        private var spanTarget = 0L               // output frames at the end of the current span

        fun feed(pcm: ByteBuffer, ptsUs: Long, fmt: MediaFormat, enc: AacEncoder) {
            if (finished) return
            if (inRate == 0) {
                inRate = fmt.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                inChannels = fmt.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                outChannels = minOf(2, inChannels)
                enc.start(outChannels)
                startSpan()
            }
            val shorts = pcm.order(ByteOrder.nativeOrder()).asShortBuffer()
            val frames = shorts.remaining() / inChannels
            val rate = inRate * k                                // asetrate: real-time sample rate
            var t0 = ptsUs / 1e6 / k                              // real time of the first frame
            var i = 0
            while (i < frames && !finished) {
                val s = spans[span]
                val ti = t0 + i / rate
                if (ti < s.start) {                               // before this span: skip
                    i = minOf(frames, i + maxOf(1, ((s.start - ti) * rate).toInt()))
                    continue
                }
                // frames of this buffer that belong to the current span
                val endIdx = minOf(frames, i + maxOf(1, kotlin.math.ceil((s.end - ti) * rate).toInt()))
                val chunk = ByteBuffer.allocateDirect((endIdx - i) * outChannels * 2).order(ByteOrder.nativeOrder())
                for (f in i until endIdx) {
                    for (c in 0 until outChannels) chunk.putShort(shorts.get(f * inChannels + c))
                }
                chunk.flip()
                process(chunk, enc)
                position = t0 + endIdx / rate
                i = endIdx
                if (position >= s.end - 0.5 / rate) endSpan(enc)
            }
        }

        private fun startSpan() {
            val s = spans[span]
            val cumOut = spans.take(span + 1).sumOf { it.out }
            spanTarget = (cumOut * OUT_RATE).roundToLong()
            val tempo = if (s.out > 0 && s.end > s.start) (s.end - s.start) / s.out else 1.0
            sonic = SonicAudioProcessor().apply {
                setSpeed(tempo.toFloat().coerceIn(0.01f, 100f))
                setPitch(1f)
                setOutputSampleRateHz(OUT_RATE)
                // asetrate: the samples are read at rate × k (rounded like the desktop)
                configure(AudioProcessor.AudioFormat((inRate * k).roundToLong().toInt(), outChannels, androidx.media3.common.C.ENCODING_PCM_16BIT))
                flush(AudioProcessor.StreamMetadata.DEFAULT)
            }
        }

        private fun process(chunk: ByteBuffer, enc: AacEncoder) {
            val p = sonic!!
            if (!p.isActive) { emit(chunk, enc); return }
            while (chunk.hasRemaining()) {
                p.queueInput(chunk)
                drain(p, enc)
            }
        }

        private fun drain(p: SonicAudioProcessor, enc: AacEncoder) {
            while (true) {
                val out = p.output
                if (!out.hasRemaining()) break
                emit(out, enc)
            }
        }

        /** Pass output on, but never beyond the current span's exact end. */
        private fun emit(buf: ByteBuffer, enc: AacEncoder) {
            val frameBytes = outChannels * 2
            val room = (spanTarget - written).coerceAtLeast(0)
            val n = minOf(room, (buf.remaining() / frameBytes).toLong()).toInt()
            if (n > 0) {
                val slice = buf.duplicate().apply { limit(position() + n * frameBytes) }
                enc.write(slice)
                written += n
            }
            buf.position(buf.limit())
        }

        private fun endSpan(enc: AacEncoder) {
            sonic?.let { p ->
                if (p.isActive) {
                    p.queueEndOfStream()
                    drain(p, enc)
                }
                p.reset()
            }
            padTo(spanTarget, enc)
            span++
            if (span >= spans.size) finished = true else startSpan()
        }

        /** Source sound ended early: finish the open span and fill the rest with silence. */
        fun finish(enc: AacEncoder) {
            if (inRate == 0) return
            while (!finished) endSpan(enc)
        }

        private fun padTo(target: Long, enc: AacEncoder) {
            val missing = target - written
            if (missing <= 0) return
            val silence = ByteBuffer.allocateDirect((missing * outChannels * 2).toInt()).order(ByteOrder.nativeOrder())
            enc.write(silence)
            written = target
        }
    }

    /**
     * AAC-LC encoder (MediaCodec, asynchronous), 48 kHz, output collected in memory. Free input
     * buffers arrive through a queue, so [write] blocks only when the encoder is really busy.
     */
    private class AacEncoder {
        private var codec: MediaCodec? = null
        private var thread: android.os.HandlerThread? = null
        private var channels = 2
        @Volatile private var format: MediaFormat? = null
        private val samples = java.util.Collections.synchronizedList(ArrayList<Encoded.Sample>())
        private val freeInputs = java.util.concurrent.LinkedBlockingQueue<Int>()
        private val done = java.util.concurrent.CountDownLatch(1)
        private val failure = java.util.concurrent.atomic.AtomicReference<Throwable?>(null)
        private var framesIn = 0L

        fun start(channels: Int) {
            this.channels = channels
            val f = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, OUT_RATE, channels).apply {
                setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
                setInteger(MediaFormat.KEY_BIT_RATE, BITRATE)
                setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 1 shl 16)
            }
            val t = android.os.HandlerThread("vsc-audio-enc").apply { start() }
            thread = t
            codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC).apply {
                setCallback(object : MediaCodec.Callback() {
                    override fun onInputBufferAvailable(codec: MediaCodec, index: Int) { freeInputs.offer(index) }
                    override fun onOutputFormatChanged(codec: MediaCodec, fmt: MediaFormat) { format = fmt }
                    override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo) {
                        if (info.size > 0 && info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0) {
                            val buf = codec.getOutputBuffer(index)!!
                            buf.position(info.offset).limit(info.offset + info.size)
                            val data = ByteArray(info.size).also { buf.get(it) }
                            samples += Encoded.Sample(data, info.presentationTimeUs, info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME)
                        }
                        codec.releaseOutputBuffer(index, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) done.countDown()
                    }
                    override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                        failure.compareAndSet(null, e)
                        done.countDown()
                        freeInputs.offer(-1)
                    }
                }, android.os.Handler(t.looper))
                configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
                start()
            }
        }

        private fun nextInput(): Int {
            val i = freeInputs.poll(5, java.util.concurrent.TimeUnit.SECONDS) ?: error("The audio encoder stopped responding")
            failure.get()?.let { throw it }
            return i
        }

        fun write(pcm: ByteBuffer) {
            val c = codec ?: return
            while (pcm.hasRemaining()) {
                val i = nextInput()
                val dst = c.getInputBuffer(i)!!
                val n = minOf(dst.remaining(), pcm.remaining()) / (channels * 2) * (channels * 2)
                val part = pcm.duplicate().apply { limit(position() + n) }
                dst.put(part)
                pcm.position(pcm.position() + n)
                c.queueInputBuffer(i, 0, n, framesIn * 1_000_000 / OUT_RATE, 0)
                framesIn += n / (channels * 2)
            }
        }

        fun finish(): Encoded? {
            val c = codec ?: return null
            c.queueInputBuffer(nextInput(), 0, 0, framesIn * 1_000_000 / OUT_RATE, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
            if (!done.await(10, java.util.concurrent.TimeUnit.SECONDS)) error("The audio encoder did not finish")
            failure.get()?.let { throw it }
            val fmt = format ?: return null
            return Encoded(fmt, withoutPriming())
        }

        /**
         * AAC encoders put a start-up delay ("priming", 2048 samples on Android = 42.7 ms) in
         * front of the sound, which would play late against the video. The delay is whatever the
         * encoder returned beyond the input (rounded up to whole 1024-sample frames); those
         * packets are dropped and the rest start at 0.
         */
        private fun withoutPriming(): List<Encoded.Sample> {
            val inFrames = (framesIn + AAC_FRAME - 1) / AAC_FRAME
            val prime = (samples.size - inFrames).toInt().coerceIn(0, samples.size)
            return samples.drop(prime).mapIndexed { i, s ->
                Encoded.Sample(s.data, i * AAC_FRAME * 1_000_000L / OUT_RATE, s.flags)
            }
        }

        fun release() {
            codec?.let { runCatching { it.stop() }; it.release() }
            codec = null
            thread?.quitSafely()
        }
    }
}
