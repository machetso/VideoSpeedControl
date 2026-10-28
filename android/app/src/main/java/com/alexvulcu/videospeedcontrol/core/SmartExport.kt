package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import java.io.FileDescriptor
import java.nio.ByteBuffer

/**
 * One smart export: copy the clip, re-encode only the sections marked `reencode` (at their
 * `outFps`), join everything into one MP4 video track. [joins] = Smart.joinPoints.
 */
data class SmartJob(
    override val info: ClipInfo,
    override val fps: Rational,
    override val trim: Trim = Trim(),
    override val segments: List<Segment> = emptyList(),
    val joins: List<Int>,
    val quality: Quality = Quality.HIGH,
) : Timing {
    override val baseRate: Rational get() = info.realFps
    override fun pieces(): List<Piece> = Segments.pieces(segments, trim.start, trimEnd, info.realFps)

    val parts: List<Smart.Part> by lazy { Smart.plan(this, joins) }

    override val outputDuration: Rational
        get() = parts.fold(Rational.ZERO) { acc, p -> acc + p.duration }

    fun blockers(): List<String> = buildList {
        if (!Smart.supported(info.videoMime)) add("Smart export needs H.264 or HEVC footage – this clip is ${info.codecName}")
        if (info.hdr != null) add("Smart export of HDR (10-bit) clips is not supported yet")
        if (joins.isEmpty()) add("No keyframe found where the parts could be joined")
        if (trim.start != 0 && trim.start !in joins) add("The in-point must be on a keyframe where a part can start")
        if (sourceFrameCount <= 0) add("The trim range is empty")
    }
}

/**
 * Smart export (desktop: SmartRunner). Copied parts: samples copied unchanged, retimed like the
 * lossless export; a copied part after an encoded one gets the source's parameter sets
 * (VPS / SPS / PPS) in front of its first keyframe – the Pixel keeps them only in the hvcC box,
 * and without them the decoder would go on with the encoder's (the desktop's 2/3-broken-frames
 * pitfall). Encoded parts: source codec and coded size (rotation stays in the container), one
 * closed GOP, parameter sets in-band, no B-frames, constant fps (frame selection as ReencodeExport).
 */
class SmartExport(
    private val context: Context,
    private val job: SmartJob,
    private val withAudio: Boolean = false,
) {
    @Volatile var cancelled = false

    fun run(fd: FileDescriptor, progress: (Float) -> Unit = {}): Int {
        val blockers = job.blockers()
        require(blockers.isEmpty()) { blockers.joinToString("; ") }
        val info = job.info
        val audioShare = if (withAudio && info.audio != null) 0.15f else 0f
        val audio = if (audioShare > 0) Audio.render(context, job, { cancelled }) { progress(it * audioShare) } else null

        val ex = MediaExtractor()
        ex.setDataSource(context, info.uri, null)
        val track = (0 until ex.trackCount).first {
            ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
        }
        val srcFormat = ex.getTrackFormat(track)
        ex.release()
        val headers = parameterSets(srcFormat)

        val muxer = MediaMuxer(fd, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        val muxFormat = MediaFormat(srcFormat).apply { removeKey(MediaFormat.KEY_DURATION) }
        muxer.setOrientationHint(info.rotation)
        val videoTrack = muxer.addTrack(muxFormat)
        val audioTrack = audio?.let { muxer.addTrack(it.format) } ?: -1
        muxer.start()
        val writer = Writer(muxer, videoTrack, audioTrack, audio)
        val total = job.parts.sumOf { it.frames }
        var done = 0
        var offset = Rational.ZERO                       // output start of the current part (s)
        try {
            for ((i, part) in job.parts.withIndex()) {
                if (cancelled) throw ExportCancelled()
                val afterEncoded = i > 0 && job.parts[i - 1].encode
                val n = if (part.encode) encodePart(part, offset, srcFormat, writer)
                else copyPart(part, offset, if (afterEncoded) headers else null, writer)
                done += n
                progress(audioShare + (1 - audioShare) * done / total)
                offset += part.duration
            }
            writer.audioUntil(Long.MAX_VALUE)
            progress(1f)
            return done
        } finally {
            try { muxer.stop() } finally { muxer.release() }
        }
    }

    /** Video samples and the pre-rendered sound, interleaved by time. */
    private class Writer(val muxer: MediaMuxer, val video: Int, val audioTrack: Int, val audio: Audio.Encoded?) {
        private var next = 0
        private val abi = MediaCodec.BufferInfo()
        fun audioUntil(us: Long) {
            val a = audio ?: return
            while (next < a.samples.size && a.samples[next].ptsUs <= us) {
                val s = a.samples[next++]
                abi.set(0, s.data.size, s.ptsUs, s.flags)
                muxer.writeSampleData(audioTrack, ByteBuffer.wrap(s.data), abi)
            }
        }
        fun video(buf: ByteBuffer, bi: MediaCodec.BufferInfo) {
            audioUntil(bi.presentationTimeUs)
            muxer.writeSampleData(video, buf, bi)
        }
    }

    /** Annex-B parameter sets of the source (HEVC: csd-0 = VPS+SPS+PPS; H.264: csd-0 SPS, csd-1 PPS). */
    private fun parameterSets(f: MediaFormat): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        for (k in listOf("csd-0", "csd-1", "csd-2")) {
            val b = f.getByteBuffer(k) ?: continue
            val a = ByteArray(b.remaining()); b.duplicate().get(a); out.write(a)
        }
        return out.toByteArray()
    }

    private fun copyPart(part: Smart.Part, offset: Rational, headers: ByteArray?, w: Writer): Int {
        val info = job.info
        val fm = info.frames
        val pieces = Segments.pieces(job.segments, part.start, part.end, info.realFps)
        val (times, end) = fm.exactTimes(info.fps)
        val retime = Segments.retimer(pieces, times, end)
        val offsetUs = (offset * Rational.of(1_000_000)).roundHalfEven()
        val startUs = fm.ptsUs[part.start]
        val endUs = if (part.end < fm.count) fm.ptsUs[part.end] else Long.MAX_VALUE
        val ex = MediaExtractor()
        try {
            ex.setDataSource(context, info.uri, null)
            val track = (0 until ex.trackCount).first {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            }
            ex.selectTrack(track)
            ex.seekTo(startUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            val buf = ByteBuffer.allocateDirect(maxOf(info.width * info.height * 2, 4 shl 20) + (headers?.size ?: 0))
            val bi = MediaCodec.BufferInfo()
            var n = 0
            var first = true
            while (true) {
                if (cancelled) throw ExportCancelled()
                val t = ex.sampleTime
                if (t < 0) break
                val sync = ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0
                if (sync && t >= endUs) break
                if (t in startUs until endUs) {
                    buf.clear()
                    if (first && headers != null) buf.put(headers)          // parameter sets in-band
                    val pos = buf.position()
                    val size = ex.readSampleData(buf, pos)
                    buf.position(0).limit(pos + size)
                    val frame = fm.indexOf(t)
                    bi.set(0, pos + size, offsetUs + retime(frame), if (sync) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                    w.video(buf, bi)
                    first = false
                    n++
                }
                if (!ex.advance()) break
            }
            return n
        } finally {
            ex.release()
        }
    }

    private fun encodePart(part: Smart.Part, offset: Rational, srcFormat: MediaFormat, w: Writer): Int {
        val info = job.info
        val fm = info.frames
        val fps = part.fps!!
        val pieces = Segments.pieces(job.segments, part.start, part.end, info.realFps)
        val offsetUs = (offset * Rational.of(1_000_000)).roundHalfEven()
        val mime = srcFormat.getString(MediaFormat.KEY_MIME)!!
        val width = srcFormat.getInteger(MediaFormat.KEY_WIDTH)
        val height = srcFormat.getInteger(MediaFormat.KEY_HEIGHT)

        fun firstTick(frame: Int): Long {
            val t = (Segments.outputTime(pieces, frame) - pieces.first().t) * fps
            val k = t.floor()
            return if (Rational.of(k) == t) k else k + 1
        }

        val encFormat = MediaFormat.createVideoFormat(mime, width, height).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            val bps = width.toDouble() * height * fps.toDouble() * job.quality.bitsPerPixel *
                (if (mime == MediaFormat.MIMETYPE_VIDEO_AVC) 1.5 else 1.0)
            setInteger(MediaFormat.KEY_BIT_RATE, bps.coerceIn(1e6, 200e6).toInt())
            setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR)
            setFloat(MediaFormat.KEY_FRAME_RATE, fps.toDouble().toFloat())
            // one closed GOP per part: only its first frame is a keyframe
            setFloat(MediaFormat.KEY_I_FRAME_INTERVAL, (part.frames / fps.toDouble() + 10).toFloat())
            setInteger(MediaFormat.KEY_PREPEND_HEADER_TO_SYNC_FRAMES, 1)
            setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0)
            // the same colour description as the copied parts: a change at the joins (Pixel:
            // sRGB transfer, the encoder's default BT.709) made players flash dark / white
            copyColorAspects(srcFormat, this)
        }
        val encName = MediaCodecList(MediaCodecList.REGULAR_CODECS).findEncoderForFormat(encFormat)
            ?: error("No ${info.codecName} encoder for ${width}×$height on this phone")
        val encoder = MediaCodec.createByCodecName(encName)
        encoder.configure(encFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        val surface = encoder.createInputSurface()
        encoder.start()
        val gl = GlFrameGrabber(width, height, surface)
        val ex = MediaExtractor()
        var decoder: MediaCodec? = null
        var config: ByteArray? = null                  // CODEC_CONFIG buffer (if not prepended)
        var written = 0
        val ebi = MediaCodec.BufferInfo()

        fun drain(untilEos: Boolean) {
            while (true) {
                val o = encoder.dequeueOutputBuffer(ebi, if (untilEos) 10_000 else 0)
                if (o == MediaCodec.INFO_TRY_AGAIN_LATER) { if (!untilEos) return else continue }
                if (o < 0) continue
                val buf = encoder.getOutputBuffer(o)!!
                buf.position(ebi.offset).limit(ebi.offset + ebi.size)
                if (ebi.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) {
                    config = ByteArray(ebi.size).also { buf.get(it) }
                } else if (ebi.size > 0) {
                    val key = ebi.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0
                    var data = ByteArray(ebi.size).also { buf.get(it) }
                    val cfg = config
                    // make sure the part's first frame carries its parameter sets in-band
                    if (key && written == 0 && cfg != null && !startsWithParameterSet(data, mime)) data = cfg + data
                    val bi = MediaCodec.BufferInfo().apply {
                        set(0, data.size, offsetUs + ebi.presentationTimeUs, if (key) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                    }
                    w.video(ByteBuffer.wrap(data), bi)
                    written++
                }
                encoder.releaseOutputBuffer(o, false)
                if (ebi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) return
            }
        }

        try {
            ex.setDataSource(context, info.uri, null)
            val track = (0 until ex.trackCount).first {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            }
            val inFormat = ex.getTrackFormat(track)
            // coded orientation: the container keeps the rotation for the whole file
            inFormat.removeKey(MediaFormat.KEY_ROTATION)
            ex.selectTrack(track)
            ex.seekTo(fm.ptsUs[part.start], MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            val dec = MediaCodec.createDecoderByType(mime)
            decoder = dec
            dec.configure(inFormat, gl.surface, null, 0)
            dec.start()
            val dbi = MediaCodec.BufferInfo()
            val endUs = if (part.end < fm.count) fm.ptsUs[part.end] else Long.MAX_VALUE
            var inputDone = false
            var nextTick = 0L
            val total = part.frames.toLong()
            while (nextTick < total) {
                if (cancelled) throw ExportCancelled()
                while (!inputDone) {
                    val i = dec.dequeueInputBuffer(0)
                    if (i < 0) break
                    val n = ex.readSampleData(dec.getInputBuffer(i)!!, 0)
                    val past = n >= 0 && ex.sampleTime >= endUs && ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0
                    if (n < 0 || past) {
                        dec.queueInputBuffer(i, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                        inputDone = true
                    } else {
                        dec.queueInputBuffer(i, 0, n, ex.sampleTime, 0)
                        ex.advance()
                    }
                }
                val o = dec.dequeueOutputBuffer(dbi, 5_000)
                if (o < 0) { drain(false); continue }
                val eos = dbi.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                val f = if (dbi.size > 0) fm.indexOf(dbi.presentationTimeUs) else -1
                val endTick = if (f >= 0 && f + 1 < part.end) minOf(firstTick(f + 1), total) else total
                val use = f >= part.start && f < part.end && nextTick < endTick
                dec.releaseOutputBuffer(o, use)
                if (use && gl.awaitFrame()) {
                    while (nextTick < endTick) {
                        gl.present((Rational.of(nextTick) / fps * Rational.of(1_000_000_000)).floor())
                        nextTick++
                        drain(false)
                    }
                }
                if (eos || (f >= 0 && f + 1 >= part.end)) break
            }
            encoder.signalEndOfInputStream()
            drain(true)
            return written
        } finally {
            decoder?.let { runCatching { it.stop() }; it.release() }
            ex.release()
            gl.release()
            runCatching { encoder.stop() }
            encoder.release()
            surface.release()
        }
    }

    /** Does an Annex-B frame start with a parameter set (HEVC VPS/SPS/PPS 32–34, H.264 SPS 7)? */
    private fun startsWithParameterSet(data: ByteArray, mime: String): Boolean {
        val i = when {
            data.size > 4 && data[0] == 0.toByte() && data[1] == 0.toByte() && data[2] == 1.toByte() -> 3
            data.size > 5 && data[0] == 0.toByte() && data[1] == 0.toByte() && data[2] == 0.toByte() && data[3] == 1.toByte() -> 4
            else -> return false
        }
        val h = data[i].toInt() and 0xff
        return if (mime == MediaFormat.MIMETYPE_VIDEO_HEVC) ((h shr 1) and 0x3f) in 32..34 else (h and 0x1f) == 7
    }
}
