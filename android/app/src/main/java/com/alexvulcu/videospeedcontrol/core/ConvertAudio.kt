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
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * Sound of "Convert videos" in pro / smart mode (user request 2026-11-04, desktop:
 * `audio.direct`): the whole clip at real-time speed, so the sound is taken straight from the
 * source – copied unchanged, or decoded and encoded once (AAC / Opus / FLAC) with the chosen
 * channels and data rate at the source's sample rate (resampled only where the codec needs it).
 * Either way it starts with the first video frame and ends with the video ([startUs], [lengthUs]).
 * (The editor's exports keep using [Audio]: stretched, 48 kHz AAC 192k.)
 */
object ConvertAudio {
    /** [mode]: "copy" | "aac" | "opus" | "flac". [channels] null = like the source. */
    data class Plan(val mode: String, val bitrateKbps: Int? = null, val channels: Int? = null)

    val MIMES = mapOf("aac" to MediaFormat.MIMETYPE_AUDIO_AAC, "opus" to MediaFormat.MIMETYPE_AUDIO_OPUS,
        "flac" to MediaFormat.MIMETYPE_AUDIO_FLAC)
    val DEFAULT_KBPS = mapOf("aac" to 192, "opus" to 160)
    /** Most channels the phone's encoders take (tested on the Pixel: AAC 6, Opus 2, FLAC 2). */
    val MAX_CHANNELS = mapOf("aac" to 6, "opus" to 2, "flac" to 2)
    private val AAC_RATES = listOf(8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)
    private val OPUS_RATES = listOf(8000, 12000, 16000, 24000, 48000)
    private const val AAC_FRAME = 1024L

    /** Sample rate written for [mode] when the source has [source] Hz. */
    fun outRate(mode: String, source: Int): Int = when (mode) {
        "aac" -> if (source in AAC_RATES) source else AAC_RATES.firstOrNull { it >= source } ?: 48000
        "opus" -> OPUS_RATES.firstOrNull { it >= source } ?: 48000
        "flac" -> source.coerceIn(8000, 192000)
        else -> source
    }

    /** The source's sound track index and format, or null. */
    fun track(ex: Extractor): Pair<Int, MediaFormat>? = (0 until ex.trackCount)
        .map { it to ex.getTrackFormat(it) }
        .firstOrNull { it.second.getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true }

    fun render(context: Context, info: ClipInfo, plan: Plan, startUs: Long, lengthUs: Long,
               isCancelled: () -> Boolean, progress: (Float) -> Unit): Audio.Encoded? {
        val ex = Extractor()
        ex.setDataSource(context, info.uri, null)
        try {
            val (track, format) = track(ex) ?: return null
            ex.selectTrack(track)
            ex.seekTo(maxOf(0L, startUs - 500_000), MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            return if (plan.mode == "copy") copy(ex, format, startUs, lengthUs, isCancelled, progress)
            else encode(ex, format, plan, startUs, lengthUs, isCancelled, progress)
        } finally {
            ex.release()
        }
    }

    private fun copy(ex: Extractor, format: MediaFormat, startUs: Long, lengthUs: Long,
                     isCancelled: () -> Boolean, progress: (Float) -> Unit): Audio.Encoded {
        val out = ArrayList<Audio.Encoded.Sample>()
        val buf = ByteBuffer.allocateDirect(1 shl 20)
        while (true) {
            if (isCancelled()) throw ExportCancelled()
            val n = ex.readSampleData(buf, 0)
            if (n < 0) break
            val t = ex.sampleTime - startUs
            if (t >= lengthUs) break
            if (t >= 0) {
                val data = ByteArray(n)
                buf.position(0); buf.get(data, 0, n); buf.clear()
                out += Audio.Encoded.Sample(data, t, MediaCodec.BUFFER_FLAG_KEY_FRAME)
                if (out.size % 200 == 0) progress((t.toFloat() / lengthUs).coerceIn(0f, 1f))
            }
            ex.advance()
        }
        progress(1f)
        return Audio.Encoded(format, out)
    }

    @OptIn(UnstableApi::class)
    private fun encode(ex: Extractor, inFormat: MediaFormat, plan: Plan, startUs: Long, lengthUs: Long,
                       isCancelled: () -> Boolean, progress: (Float) -> Unit): Audio.Encoded? {
        val mime = MIMES[plan.mode] ?: error("Unknown sound codec ${plan.mode}")
        val thread = android.os.HandlerThread("vsc-convert-audio").apply { start() }
        val outputs = LinkedBlockingQueue<Pair<Int, MediaCodec.BufferInfo>>()
        val failure = java.util.concurrent.atomic.AtomicReference<Throwable?>(null)
        val decoder = MediaCodec.createDecoderByType(inFormat.getString(MediaFormat.KEY_MIME)!!)
        inFormat.setInteger(MediaFormat.KEY_PCM_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
        val endUs = startUs + lengthUs
        decoder.setCallback(object : MediaCodec.Callback() {
            private var inputDone = false
            override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
                if (inputDone) return
                try {
                    val n = ex.readSampleData(codec.getInputBuffer(index)!!, 0)
                    if (n < 0 || ex.sampleTime > endUs + 200_000) {
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
        decoder.start()

        var encoder: Encoder? = null
        var sonic: SonicAudioProcessor? = null
        var inRate = 0
        var inCh = 0
        var outCh = 0
        var outRate = 0
        var srcFramesWanted = 0L          // source-rate frames from startUs to the end
        var srcFramesDone = 0L
        var outFramesWanted = 0L
        try {
            fun emit(pcm: ByteBuffer) {
                val enc = encoder!!
                val s = sonic
                if (s == null || !s.isActive) { enc.write(pcm); return }
                while (pcm.hasRemaining()) {
                    s.queueInput(pcm)
                    while (true) { val o = s.output; if (!o.hasRemaining()) break; enc.write(o) }
                }
            }
            /** Source frames [a, b) of this chunk mixed to [outCh] and passed on (silence if null). */
            fun pass(shorts: java.nio.ShortBuffer?, a: Int, b: Int) {
                if (b <= a) return
                val chunk = ByteBuffer.allocateDirect((b - a) * outCh * 2).order(ByteOrder.nativeOrder())
                if (shorts != null) mix(shorts, a, b, inCh, outCh, chunk) else repeat((b - a) * outCh) { chunk.putShort(0) }
                chunk.flip()
                emit(chunk)
                srcFramesDone += b - a
            }
            while (true) {
                if (isCancelled()) throw ExportCancelled()
                val (o, bi) = outputs.poll(5, TimeUnit.SECONDS) ?: error("The audio decoder stopped responding")
                failure.get()?.let { throw it }
                if (o < 0) break
                if (bi.size > 0) {
                    val fmt = decoder.getOutputFormat(o)
                    if (encoder == null) {
                        inRate = fmt.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                        inCh = fmt.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                        outCh = minOf(plan.channels ?: inCh, inCh, MAX_CHANNELS.getValue(plan.mode))
                        outRate = outRate(plan.mode, inRate)
                        srcFramesWanted = Math.round(lengthUs * inRate / 1e6)
                        outFramesWanted = Math.round(lengthUs * outRate / 1e6)
                        if (outRate != inRate) sonic = SonicAudioProcessor().apply {
                            setSpeed(1f); setPitch(1f); setOutputSampleRateHz(outRate)
                            configure(AudioProcessor.AudioFormat(inRate, outCh, androidx.media3.common.C.ENCODING_PCM_16BIT))
                            flush(AudioProcessor.StreamMetadata.DEFAULT)
                        }
                        encoder = Encoder(mime, outRate, outCh, (plan.bitrateKbps ?: DEFAULT_KBPS[plan.mode] ?: 0) * 1000)
                    }
                    val buf = decoder.getOutputBuffer(o)!!
                    buf.position(bi.offset).limit(bi.offset + bi.size)
                    val shorts = buf.order(ByteOrder.nativeOrder()).asShortBuffer()
                    val frames = shorts.remaining() / inCh
                    // where this chunk starts, in source frames from startUs
                    val at = Math.round((bi.presentationTimeUs - startUs) * inRate / 1e6)
                    if (at > srcFramesDone) {                       // a gap (or a late start): silence
                        val gap = minOf(at - srcFramesDone, srcFramesWanted - srcFramesDone).toInt()
                        var left = gap
                        while (left > 0) { val n = minOf(left, 65536); pass(null, 0, n); left -= n }
                    }
                    val skip = (srcFramesDone - at).coerceIn(0, frames.toLong()).toInt()   // before startUs / overlap
                    val take = minOf(frames.toLong(), skip + srcFramesWanted - srcFramesDone).toInt()
                    pass(shorts, skip, take)
                    progress((srcFramesDone.toFloat() / maxOf(1, srcFramesWanted)).coerceIn(0f, 1f))
                }
                decoder.releaseOutputBuffer(o, false)
                if (bi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0 || (encoder != null && srcFramesDone >= srcFramesWanted)) break
            }
            val enc = encoder ?: return null
            var left = (srcFramesWanted - srcFramesDone).toInt()                  // sound ended early
            while (left > 0) { val n = minOf(left, 65536); pass(null, 0, n); left -= n }
            sonic?.let { s ->
                if (s.isActive) {
                    s.queueEndOfStream()
                    while (true) { val o = s.output; if (!o.hasRemaining()) break; enc.write(o) }
                }
            }
            progress(1f)
            return enc.finish(outFramesWanted)
        } finally {
            runCatching { decoder.stop() }
            decoder.release()
            encoder?.release()
            thread.quitSafely()
        }
    }

    /**
     * Frames [a, b) of interleaved 16-bit [src] with [inCh] channels → [outCh] channels into
     * [dst]. Fewer channels: 5.1 / 7.1 (Android order FL FR FC LFE BL BR …) → stereo with the
     * centre and the surrounds at −3 dB, scaled to stay below full scale; → mono = mean of the
     * stereo mix; otherwise the first channels are kept. Never more channels than the source.
     */
    fun mix(src: java.nio.ShortBuffer, a: Int, b: Int, inCh: Int, outCh: Int, dst: ByteBuffer) {
        val base = src.position()
        fun s(f: Int, c: Int) = src.get(base + f * inCh + c).toInt()
        for (f in a until b) {
            when {
                outCh == inCh -> for (c in 0 until inCh) dst.putShort(s(f, c).toShort())
                outCh <= 2 && inCh > 2 -> {
                    val c = if (inCh >= 3) s(f, 2) * 0.7071 else 0.0
                    val bl = if (inCh >= 6) s(f, 4) * 0.7071 else 0.0
                    val br = if (inCh >= 6) s(f, 5) * 0.7071 else 0.0
                    val norm = 1.0 / (1.0 + 0.7071 + if (inCh >= 6) 0.7071 else 0.0)
                    val l = (s(f, 0) + c + bl) * norm
                    val r = (s(f, 1) + c + br) * norm
                    if (outCh == 1) dst.putShort(clip((l + r) / 2))
                    else { dst.putShort(clip(l)); dst.putShort(clip(r)) }
                }
                outCh == 1 -> dst.putShort(clip((s(f, 0) + s(f, 1)) / 2.0))
                else -> for (c in 0 until outCh) dst.putShort(s(f, c).toShort())
            }
        }
    }

    private fun clip(v: Double): Short = Math.round(v).coerceIn(-32768, 32767).toShort()

    /** MediaCodec sound encoder (asynchronous), output collected in memory (like Audio's AAC encoder). */
    private class Encoder(val mime: String, val rate: Int, val channels: Int, bitrate: Int) {
        private val thread = android.os.HandlerThread("vsc-convert-audio-enc").apply { start() }
        @Volatile private var format: MediaFormat? = null
        private val samples = java.util.Collections.synchronizedList(ArrayList<Audio.Encoded.Sample>())
        private val freeInputs = LinkedBlockingQueue<Int>()
        private val done = java.util.concurrent.CountDownLatch(1)
        private val failure = java.util.concurrent.atomic.AtomicReference<Throwable?>(null)
        private var framesIn = 0L
        private val codec: MediaCodec

        init {
            val f = MediaFormat.createAudioFormat(mime, rate, channels).apply {
                if (mime == MediaFormat.MIMETYPE_AUDIO_AAC) setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
                if (bitrate > 0) setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
                setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 1 shl 16)
            }
            codec = MediaCodec.createEncoderByType(mime).apply {
                setCallback(object : MediaCodec.Callback() {
                    override fun onInputBufferAvailable(codec: MediaCodec, index: Int) { freeInputs.offer(index) }
                    override fun onOutputFormatChanged(codec: MediaCodec, fmt: MediaFormat) { format = fmt }
                    override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo) {
                        if (info.size > 0 && info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0) {
                            val buf = codec.getOutputBuffer(index)!!
                            buf.position(info.offset).limit(info.offset + info.size)
                            val data = ByteArray(info.size).also { buf.get(it) }
                            samples += Audio.Encoded.Sample(data, info.presentationTimeUs, MediaCodec.BUFFER_FLAG_KEY_FRAME)
                        }
                        codec.releaseOutputBuffer(index, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) done.countDown()
                    }
                    override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                        failure.compareAndSet(null, e)
                        done.countDown()
                        freeInputs.offer(-1)
                    }
                }, android.os.Handler(thread.looper))
                configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
                start()
            }
        }

        private fun nextInput(): Int {
            val i = freeInputs.poll(5, TimeUnit.SECONDS) ?: error("The audio encoder stopped responding")
            failure.get()?.let { throw it }
            if (i < 0) failure.get()?.let { throw it }
            return i
        }

        fun write(pcm: ByteBuffer) {
            val fb = channels * 2
            while (pcm.hasRemaining()) {
                val i = nextInput()
                val dst = codec.getInputBuffer(i)!!
                val n = minOf(dst.remaining(), pcm.remaining()) / fb * fb
                dst.put(pcm.duplicate().apply { limit(position() + n) })
                pcm.position(pcm.position() + n)
                codec.queueInputBuffer(i, 0, n, framesIn * 1_000_000 / rate, 0)
                framesIn += n / fb
            }
        }

        /** Ends the stream; [frames] = exact length at [rate] (pads with silence when short). */
        fun finish(frames: Long): Audio.Encoded? {
            if (framesIn < frames) write(ByteBuffer.allocateDirect(((frames - framesIn) * channels * 2).toInt()).order(ByteOrder.nativeOrder()))
            codec.queueInputBuffer(nextInput(), 0, 0, framesIn * 1_000_000 / rate, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
            if (!done.await(10, TimeUnit.SECONDS)) error("The audio encoder did not finish")
            failure.get()?.let { throw it }
            val fmt = format ?: return null
            return Audio.Encoded(fmt, if (mime == MediaFormat.MIMETYPE_AUDIO_AAC) withoutPriming() else samples.toList())
        }

        /** AAC priming (see Audio's encoder): packets beyond the input are the start-up delay. */
        private fun withoutPriming(): List<Audio.Encoded.Sample> {
            val inFrames = (framesIn + AAC_FRAME - 1) / AAC_FRAME
            val prime = (samples.size - inFrames).toInt().coerceIn(0, samples.size)
            return samples.drop(prime).mapIndexed { i, s ->
                Audio.Encoded.Sample(s.data, i * AAC_FRAME * 1_000_000L / rate, s.flags)
            }
        }

        fun release() {
            runCatching { codec.stop() }
            codec.release()
            thread.quitSafely()
        }
    }
}
