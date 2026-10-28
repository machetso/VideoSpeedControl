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
        if (job is SmartJob) {
            // re-encoded parts last whole frames at their rate (Smart.plan) – the sound follows
            return job.parts.flatMap { part ->
                val ps = Segments.pieces(job.segments, part.start, part.end, job.info.realFps)
                val scale = if (part.encode) (part.duration / Segments.duration(ps)).toDouble() else 1.0
                ps.map { p ->
                    Span(fileTime(job.info, p.start) / k, fileTime(job.info, p.end) / k,
                        (Rational.of((p.end - p.start).toLong()) / p.rate).toDouble() * scale)
                }
            }
        }
        val spans = if (!job.hasSegments) {
            listOf(Span(fileTime(job.info, job.trim.start) / k, fileTime(job.info, job.trimEnd) / k,
                job.outputDuration.toDouble()))
        } else job.pieces().map { p ->
            Span(fileTime(job.info, p.start) / k, fileTime(job.info, p.end) / k,
                (Rational.of((p.end - p.start).toLong()) / p.rate).toDouble())
        }
        // re-encoded video lasts a whole number of frames – the sound ends exactly with it
        if (job is ReencodeJob) {
            val video = job.outputFrameCount / job.fps.toDouble()
            val last = spans.last()
            val out = last.out + video - spans.sumOf { it.out }
            if (out > 0) return spans.dropLast(1) + last.copy(out = out)
        }
        return spans
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
            ex.seekTo(maxOf(0L, (((spans.first().start - CONTEXT) * k - 0.2) * 1e6).toLong()), MediaExtractor.SEEK_TO_PREVIOUS_SYNC)

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
                        if (n < 0 || ex.sampleTime / 1e6 / k > lastSpanEnd + CONTEXT + 0.2) {
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

    /** Seconds of real-time sound fed before and after every stretched span (Sonic warm-up). */
    const val CONTEXT = 0.25

    private val leadCache = java.util.concurrent.ConcurrentHashMap<Pair<Int, Int>, Double>()

    /**
     * How far Sonic moves the content early, in seconds of input, for input rate [inRate] (Hz,
     * already × slow-mo factor) and [tempo] – measured once with a click through a processor set
     * up exactly like the real one (in-process, a few ms) and cached. Measured on a Pixel:
     * ~4–5 ms of input, i.e. 32 ms early at 8× slower, 190 ms at 40× (desktop: rubberband,
     * same idea). The onset is aligned – what the ear times in a smeared click.
     */
    @OptIn(UnstableApi::class)
    fun sonicLead(inRate: Int, tempo: Double): Double = leadCache.getOrPut(inRate to (tempo * 1e6).toInt()) {
        val click = CONTEXT
        val frames = ((click + 0.2) * inRate).toInt()
        val input = ByteBuffer.allocateDirect(frames * 4).order(ByteOrder.nativeOrder())
        val at = (click * inRate).toInt()
        for (i in 0 until frames) {
            val v: Short = if (i in at until at + maxOf(1, inRate / 2000)) 29000 else 0
            input.putShort(v); input.putShort(v)
        }
        input.flip()
        val p = SonicAudioProcessor().apply {
            setSpeed(tempo.toFloat()); setPitch(1f); setOutputSampleRateHz(OUT_RATE)
            configure(AudioProcessor.AudioFormat(inRate, 2, androidx.media3.common.C.ENCODING_PCM_16BIT))
            flush(AudioProcessor.StreamMetadata.DEFAULT)
        }
        if (!p.isActive) return@getOrPut 0.0              // tempo 1, no rate change: pass-through
        val out = java.io.ByteArrayOutputStream()
        fun drain() {
            while (true) {
                val o = p.output
                if (!o.hasRemaining()) break
                val b = ByteArray(o.remaining()); o.get(b); out.write(b)
            }
        }
        while (input.hasRemaining()) { p.queueInput(input); drain() }
        p.queueEndOfStream(); drain()
        val pcm = ByteBuffer.wrap(out.toByteArray()).order(ByteOrder.nativeOrder()).asShortBuffer()
        val n = pcm.remaining() / 2
        var peak = 0; var level = 0
        for (i in 0 until n) { val v = kotlin.math.abs(pcm.get(i * 2).toInt()); if (v > level) { level = v; peak = i } }
        if (level < 3000) 0.0 else {
            var onset = peak
            for (i in 0..peak) if (kotlin.math.abs(pcm.get(i * 2).toInt()) > level / 2) { onset = i; break }
            click - onset.toDouble() / OUT_RATE * tempo
        }
    }

    /**
     * Cuts the decoded sound into spans and time-stretches each one; output is 48 kHz stereo
     * (or mono) 16-bit PCM handed to the encoder, each span exactly as long as its video piece
     * (lengths from the running total, so rounding never adds up).
     *
     * Every span gets its own Sonic fed from [CONTEXT] before its start to [CONTEXT] after its
     * end, so neighbouring spans overlap: while one still takes its after-context the next has
     * already started – its output is held back until the earlier span is complete. The first
     * output frames (context minus Sonic's lead, see [sonicLead]) are dropped.
     */
    @OptIn(UnstableApi::class)
    private class Stretcher(val spans: List<Span>, val k: Double) {
        var finished = false
        var position = spans.first().start        // real-time seconds reached in the input
        private var inRate = 0
        private var inChannels = 0
        private var outChannels = 0
        private var procs: List<Proc> = emptyList()
        private var current = 0                   // span whose output goes to the encoder now
        private var enc: AacEncoder? = null

        /** One span's processor: input window [inStart, inEnd) in real-time seconds. */
        private inner class Proc(val index: Int) {
            val span = spans[index]
            val tempo = if (span.out > 0 && span.end > span.start) (span.end - span.start) / span.out else 1.0
            val inStart = maxOf(0.0, span.start - CONTEXT)
            val inEnd = span.end + CONTEXT
            /** Output frames this span must produce (from the running total). */
            val target: Long = run {
                val before = spans.take(index).sumOf { it.out }
                kotlin.math.round((before + span.out) * OUT_RATE).toLong() - kotlin.math.round(before * OUT_RATE).toLong()
            }
            var sonic: SonicAudioProcessor? = null
            var skip = 0L                         // output frames still to drop at the start
            var written = 0L                      // frames delivered (to the encoder or held)
            val held = java.io.ByteArrayOutputStream()
            var inputDone = false

            fun start() {
                val rate = (inRate * k).roundToLong().toInt()
                val pre = span.start - inStart
                val lead = sonicLead(rate, tempo)
                val first = (pre - lead) / tempo                 // output time of the span start
                sonic = SonicAudioProcessor().apply {
                    setSpeed(tempo.toFloat().coerceIn(0.01f, 100f))
                    setPitch(1f)
                    setOutputSampleRateHz(OUT_RATE)
                    // asetrate: the samples are read at rate × k (rounded like the desktop)
                    configure(AudioProcessor.AudioFormat(rate, outChannels, androidx.media3.common.C.ENCODING_PCM_16BIT))
                    flush(AudioProcessor.StreamMetadata.DEFAULT)
                }
                if (first >= 0) skip = kotlin.math.round(first * OUT_RATE).toLong()
                else deliver(ByteBuffer.allocateDirect((kotlin.math.round(-first * OUT_RATE) * outChannels * 2).toInt()))
            }

            fun feed(chunk: ByteBuffer) {
                val p = sonic!!
                if (!p.isActive) { take(chunk); return }
                while (chunk.hasRemaining()) {
                    p.queueInput(chunk)
                    drain()
                }
            }

            fun end() {
                if (inputDone) return
                inputDone = true
                sonic?.let { p ->
                    if (p.isActive) { p.queueEndOfStream(); drain() }
                    p.reset()
                }
                // a short result is padded with silence
                val missing = target - written
                if (missing > 0) deliver(ByteBuffer.allocateDirect((missing * outChannels * 2).toInt()))
            }

            private fun drain() {
                val p = sonic!!
                while (true) {
                    val o = p.output
                    if (!o.hasRemaining()) break
                    take(o)
                }
            }

            /** Drop the lead-in, then deliver at most [target] frames. */
            private fun take(buf: ByteBuffer) {
                val fb = outChannels * 2
                val n = buf.remaining() / fb
                val drop = minOf(skip, n.toLong()).toInt()
                skip -= drop
                buf.position(buf.position() + drop * fb)
                deliver(buf)
            }

            private fun deliver(buf: ByteBuffer) {
                val fb = outChannels * 2
                val room = (target - written).coerceAtLeast(0)
                val n = minOf(room, (buf.remaining() / fb).toLong()).toInt()
                if (n > 0) {
                    val slice = buf.duplicate().apply { limit(position() + n * fb) }
                    if (index == current) enc!!.write(slice)
                    else { val b = ByteArray(n * fb); slice.get(b); held.write(b) }
                    written += n
                }
                buf.position(buf.limit())
            }
        }

        fun feed(pcm: ByteBuffer, ptsUs: Long, fmt: MediaFormat, encoder: AacEncoder) {
            if (finished) return
            if (inRate == 0) {
                inRate = fmt.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                inChannels = fmt.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                outChannels = minOf(2, inChannels)
                enc = encoder
                encoder.start(outChannels)
                procs = spans.indices.map { Proc(it) }
            }
            val shorts = pcm.order(ByteOrder.nativeOrder()).asShortBuffer()
            val frames = shorts.remaining() / inChannels
            val rate = inRate * k                                // asetrate: real-time sample rate
            val t0 = ptsUs / 1e6 / k                              // real time of the first frame
            val t1 = t0 + frames / rate
            position = t1
            for (p in procs) {
                if (p.inputDone || p.inEnd <= t0) { if (!p.inputDone && p.inEnd <= t0) p.end(); continue }
                if (p.inStart >= t1) break                       // later spans: not reached yet
                if (p.sonic == null) p.start()
                val a = maxOf(0, kotlin.math.ceil((p.inStart - t0) * rate).toInt()).coerceAtMost(frames)
                val b = minOf(frames, kotlin.math.ceil((p.inEnd - t0) * rate).toInt()).coerceAtLeast(a)
                if (b > a) {
                    val chunk = ByteBuffer.allocateDirect((b - a) * outChannels * 2).order(ByteOrder.nativeOrder())
                    for (f in a until b) for (c in 0 until outChannels) chunk.putShort(shorts.get(f * inChannels + c))
                    chunk.flip()
                    p.feed(chunk)
                }
                if (p.inEnd <= t1) p.end()
            }
            advance()
        }

        /** Hand finished spans to the encoder in order, releasing the held output of the next. */
        private fun advance() {
            while (current < procs.size && procs[current].inputDone) {
                current++
                if (current < procs.size) {
                    val next = procs[current]
                    if (next.held.size() > 0) enc!!.write(ByteBuffer.wrap(next.held.toByteArray()))
                    next.held.reset()
                }
            }
            if (current >= procs.size) finished = true
        }

        /** Source sound ended early: finish the open spans (padded with silence). */
        fun finish(encoder: AacEncoder) {
            if (inRate == 0) return
            for (p in procs) {
                if (p.sonic == null) p.start()
                p.end()
            }
            advance()
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
