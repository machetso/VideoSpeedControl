package com.alexvulcu.videospeedcontrol.core

import android.media.MediaCodec
import android.media.MediaFormat
import java.io.ByteArrayOutputStream
import java.io.FileDescriptor
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.channels.FileChannel

/**
 * Matroska (.mkv) writer (user request 2026-11-04: Convert videos, pro mode). Android has no MKV
 * muxer – MediaMuxer writes MP4 / WebM / 3GP / OGG, and neither MediaMuxer nor Media3's
 * Mp4Muxer takes MP3 (tested on the Pixel) – so copying the sound of old DivX / Xvid files
 * unchanged needs MKV.
 *
 * Layout: EBML header, Segment { SeekHead (in a reserved Void), Info (Duration patched at the
 * end), Tracks, Clusters (SimpleBlocks, a new cluster at a video keyframe after ≥ 1 s), Cues }.
 * Timestamps in ms (TimestampScale 1 000 000 ns, like FFmpeg's MKV). The output must be
 * seekable (MediaStore files are): sizes and the seek head are written last.
 *
 * Encoder output is converted to what Matroska expects: H.264 / HEVC Annex-B (start codes) →
 * 4-byte lengths with an avcC / hvcC built from the parameter sets; AV1 without temporal
 * delimiter OBUs (av1C = MediaCodec's csd-0); Opus: Android wraps the OpusHead in its own
 * "AOPUSHDR" markers – unwrapped.
 */
class MkvMuxer(fd: FileDescriptor) : OutMuxer {
    private val out = FileOutputStream(fd)
    private val channel: FileChannel = out.channel.apply { position(0); truncate(0) }
    private val tracks = ArrayList<Track>()
    private var started = false
    private var segmentData = 0L               // file offset of the Segment's content
    private var segmentSizeAt = 0L
    private var seekHeadAt = 0L
    private var durationAt = 0L
    private var infoPos = 0L
    private var tracksPos = 0L
    private var cluster: ByteArrayOutputStream? = null
    private var clusterMs = 0L
    private var lastMs = 0L
    private val cues = ArrayList<Pair<Long, Long>>()     // (time ms, cluster position)
    private var videoTrack = -1

    private class Track(val number: Int, val format: MediaFormat, val kind: Mkv.Kind)

    override fun addTrack(format: MediaFormat): Int {
        check(!started) { "Tracks must be added before start()" }
        val kind = Mkv.kind(format)
        tracks += Track(tracks.size + 1, format, kind)
        if (kind.video && videoTrack < 0) videoTrack = tracks.size - 1
        return tracks.size - 1
    }

    override fun start() {
        started = true
        write(Mkv.ebmlHeader())
        segmentSizeAt = channel.position() + 4
        write(Mkv.id(Mkv.SEGMENT) + Mkv.UNKNOWN_SIZE8)
        segmentData = channel.position()
        seekHeadAt = channel.position()
        write(Mkv.void(SEEK_HEAD_ROOM))
        infoPos = channel.position() - segmentData
        val (info, durationOffset) = Mkv.info()
        durationAt = channel.position() + durationOffset
        write(info)
        tracksPos = channel.position() - segmentData
        write(Mkv.element(Mkv.TRACKS, tracks.fold(ByteArray(0)) { acc, t -> acc + Mkv.trackEntry(t.number, t.format, t.kind) }))
    }

    override fun writeSampleData(track: Int, buf: ByteBuffer, info: MediaCodec.BufferInfo) {
        check(started) { "start() first" }
        if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0 || info.size == 0) return
        val t = tracks[track]
        val raw = ByteArray(info.size)
        buf.duplicate().apply { position(info.offset); limit(info.offset + info.size) }.get(raw)
        val data = Mkv.frameData(t.kind, raw)
        val ms = Math.round(info.presentationTimeUs / 1000.0)
        val key = !t.kind.video || info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0
        val c = cluster
        val newCluster = c == null || ms - clusterMs > 30_000 || ms - clusterMs < -30_000 || c.size() > (8 shl 20) ||
            (t.kind.video && key && ms - clusterMs >= 1000)
        if (newCluster) {
            flushCluster()
            cluster = ByteArrayOutputStream().apply { write(Mkv.element(Mkv.TIMESTAMP, Mkv.uint(maxOf(0, ms)))) }
            clusterMs = maxOf(0, ms)
            if (t.kind.video || videoTrack < 0) cues += clusterMs to (channel.position() - segmentData)
        }
        cluster!!.write(Mkv.simpleBlock(t.number, (ms - clusterMs).toInt(), key, data))
        lastMs = maxOf(lastMs, ms + frameMs(t))
    }

    private fun frameMs(t: Track): Long {
        val f = t.format
        if (t.kind.video && f.containsKey(MediaFormat.KEY_FRAME_RATE)) {
            val fps = runCatching { f.getFloat(MediaFormat.KEY_FRAME_RATE).toDouble() }
                .getOrElse { f.getInteger(MediaFormat.KEY_FRAME_RATE).toDouble() }
            if (fps > 0) return Math.round(1000 / fps)
        }
        return 0
    }

    private fun flushCluster() {
        val c = cluster ?: return
        write(Mkv.element(Mkv.CLUSTER, c.toByteArray()))
        cluster = null
    }

    override fun stop() {
        if (!started) return
        flushCluster()
        val cuesPos = channel.position() - segmentData
        if (cues.isNotEmpty()) write(Mkv.cues(cues, (if (videoTrack >= 0) videoTrack else 0) + 1))
        val end = channel.position()
        // segment size, duration, seek head
        writeAt(segmentSizeAt, Mkv.size8(end - segmentData))
        writeAt(durationAt, Mkv.float64(lastMs.toDouble()))
        val seeks = mutableListOf(Mkv.INFO to infoPos, Mkv.TRACKS to tracksPos)
        if (cues.isNotEmpty()) seeks += Mkv.CUES to cuesPos
        val head = Mkv.seekHead(seeks)
        writeAt(seekHeadAt, head + Mkv.void(SEEK_HEAD_ROOM - head.size))
        channel.position(end)
        channel.force(true)
        started = false
    }

    override fun release() {
        runCatching { out.close() }
    }

    private fun write(b: ByteArray) {
        val bb = ByteBuffer.wrap(b)
        while (bb.hasRemaining()) channel.write(bb)
    }

    private fun writeAt(pos: Long, b: ByteArray) {
        val bb = ByteBuffer.wrap(b)
        var p = pos
        while (bb.hasRemaining()) p += channel.write(bb, p)
    }

    private companion object {
        const val SEEK_HEAD_ROOM = 96
    }
}

/** Matroska building blocks (pure, unit-tested on the JVM). */
object Mkv {
    const val EBML = 0x1A45DFA3L
    const val SEGMENT = 0x18538067L
    const val SEEK_HEAD = 0x114D9B74L
    const val SEEK = 0x4DBBL
    const val SEEK_ID = 0x53ABL
    const val SEEK_POSITION = 0x53ACL
    const val VOID = 0xECL
    const val INFO = 0x1549A966L
    const val TIMESTAMP_SCALE = 0x2AD7B1L
    const val DURATION = 0x4489L
    const val MUXING_APP = 0x4D80L
    const val WRITING_APP = 0x5741L
    const val TRACKS = 0x1654AE6BL
    const val TRACK_ENTRY = 0xAEL
    const val TRACK_NUMBER = 0xD7L
    const val TRACK_UID = 0x73C5L
    const val TRACK_TYPE = 0x83L
    const val FLAG_LACING = 0x9CL
    const val DEFAULT_DURATION = 0x23E383L
    const val CODEC_ID = 0x86L
    const val CODEC_PRIVATE = 0x63A2L
    const val CODEC_DELAY = 0x56AAL
    const val SEEK_PRE_ROLL = 0x56BBL
    const val LANGUAGE = 0x22B59CL
    const val VIDEO = 0xE0L
    const val PIXEL_WIDTH = 0xB0L
    const val PIXEL_HEIGHT = 0xBAL
    const val AUDIO = 0xE1L
    const val SAMPLING_FREQUENCY = 0xB5L
    const val CHANNELS = 0x9FL
    const val CLUSTER = 0x1F43B675L
    const val TIMESTAMP = 0xE7L
    const val SIMPLE_BLOCK = 0xA3L
    const val CUES = 0x1C53BB6BL
    const val CUE_POINT = 0xBBL
    const val CUE_TIME = 0xB3L
    const val CUE_TRACK_POSITIONS = 0xB7L
    const val CUE_TRACK = 0xF7L
    const val CUE_CLUSTER_POSITION = 0xF1L

    /** Size field "unknown / patched later": 8 bytes. */
    val UNKNOWN_SIZE8 = byteArrayOf(0x01, 0xFF.toByte(), 0xFF.toByte(), 0xFF.toByte(), 0xFF.toByte(),
        0xFF.toByte(), 0xFF.toByte(), 0xFF.toByte())

    enum class Kind(val codecId: String, val video: Boolean) {
        AVC("V_MPEG4/ISO/AVC", true), HEVC("V_MPEGH/ISO/HEVC", true), AV1("V_AV1", true),
        VP9("V_VP9", true), AAC("A_AAC", false), OPUS("A_OPUS", false), FLAC("A_FLAC", false),
        MP3("A_MPEG/L3", false), MP2("A_MPEG/L2", false), AC3("A_AC3", false), EAC3("A_EAC3", false),
        DTS("A_DTS", false), VORBIS("A_VORBIS", false),
    }

    /** Sound codecs (MediaFormat mime) MKV takes here – [OutMuxer.canHold] uses it. */
    val AUDIO_MIMES = mapOf(
        MediaFormat.MIMETYPE_AUDIO_AAC to Kind.AAC, MediaFormat.MIMETYPE_AUDIO_OPUS to Kind.OPUS,
        MediaFormat.MIMETYPE_AUDIO_FLAC to Kind.FLAC, MediaFormat.MIMETYPE_AUDIO_MPEG to Kind.MP3,
        "audio/mpeg-L2" to Kind.MP2, MediaFormat.MIMETYPE_AUDIO_AC3 to Kind.AC3,
        MediaFormat.MIMETYPE_AUDIO_EAC3 to Kind.EAC3, "audio/vnd.dts" to Kind.DTS,
        MediaFormat.MIMETYPE_AUDIO_VORBIS to Kind.VORBIS,
    )

    fun kind(format: MediaFormat): Kind = when (val mime = format.getString(MediaFormat.KEY_MIME)) {
        MediaFormat.MIMETYPE_VIDEO_AVC -> Kind.AVC
        MediaFormat.MIMETYPE_VIDEO_HEVC -> Kind.HEVC
        MediaFormat.MIMETYPE_VIDEO_AV1 -> Kind.AV1
        MediaFormat.MIMETYPE_VIDEO_VP9 -> Kind.VP9
        else -> AUDIO_MIMES[mime] ?: throw IllegalArgumentException("$mime can't be stored in MKV")
    }

    // ------------------------------------------------------------------ EBML primitives
    fun id(id: Long): ByteArray {
        val n = when { id > 0xFFFFFF -> 4; id > 0xFFFF -> 3; id > 0xFF -> 2; else -> 1 }
        return ByteArray(n) { ((id shr (8 * (n - 1 - it))) and 0xFF).toByte() }
    }

    /** Variable-size integer (shortest form; the all-ones value of a length is reserved). */
    fun size(v: Long): ByteArray {
        var n = 1
        while (n < 8 && v >= (1L shl (7 * n)) - 1) n++
        return sizeN(v, n)
    }

    fun size8(v: Long) = sizeN(v, 8)

    private fun sizeN(v: Long, n: Int): ByteArray {
        val marked = v or (1L shl (7 * n))
        return ByteArray(n) { ((marked shr (8 * (n - 1 - it))) and 0xFF).toByte() }
    }

    fun uint(v: Long): ByteArray {
        var n = 1
        while (n < 8 && v ushr (8 * n) != 0L) n++
        return ByteArray(n) { ((v shr (8 * (n - 1 - it))) and 0xFF).toByte() }
    }

    fun float64(v: Double): ByteArray = ByteBuffer.allocate(8).putDouble(v).array()

    fun element(id: Long, data: ByteArray): ByteArray = id(id) + size(data.size.toLong()) + data
    private fun uintEl(id: Long, v: Long) = element(id, uint(v))
    private fun strEl(id: Long, s: String) = element(id, s.toByteArray(Charsets.UTF_8))

    /** A Void element of exactly [total] bytes (≥ 2). */
    fun void(total: Int): ByteArray {
        require(total >= 2)
        val sizeLen = if (total - 2 < 127) 1 else if (total - 3 < 16383) 2 else 8
        val body = total - 1 - sizeLen
        return id(VOID) + sizeN(body.toLong(), sizeLen) + ByteArray(body)
    }

    fun ebmlHeader(): ByteArray = element(EBML,
        uintEl(0x4286, 1) + uintEl(0x42F7, 1) + uintEl(0x42F2, 4) + uintEl(0x42F3, 8) +
            strEl(0x4282, "matroska") + uintEl(0x4287, 4) + uintEl(0x4285, 2))

    /** Info element and the offset of its Duration value (patched by the muxer at the end). */
    fun info(): Pair<ByteArray, Int> {
        val scale = uintEl(TIMESTAMP_SCALE, 1_000_000)
        val app = strEl(MUXING_APP, "VideoSpeedControl") + strEl(WRITING_APP, "VideoSpeedControl (Android)")
        val durHead = id(DURATION) + size(8)
        val body = scale + durHead + float64(0.0) + app
        val head = id(INFO) + size(body.size.toLong())
        return head + body to head.size + scale.size + durHead.size
    }

    fun trackEntry(number: Int, f: MediaFormat, kind: Kind): ByteArray {
        var body = uintEl(TRACK_NUMBER, number.toLong()) + uintEl(TRACK_UID, 0x5643_0000L + number) +
            uintEl(TRACK_TYPE, if (kind.video) 1 else 2) + uintEl(FLAG_LACING, 0) +
            strEl(LANGUAGE, "und") + strEl(CODEC_ID, kind.codecId)
        codecPrivate(f, kind)?.let { body += element(CODEC_PRIVATE, it) }
        if (kind.video) {
            if (f.containsKey(MediaFormat.KEY_FRAME_RATE)) {
                val fps = runCatching { f.getFloat(MediaFormat.KEY_FRAME_RATE).toDouble() }
                    .getOrElse { f.getInteger(MediaFormat.KEY_FRAME_RATE).toDouble() }
                if (fps > 0) body += uintEl(DEFAULT_DURATION, Math.round(1e9 / fps))
            }
            body += element(VIDEO, uintEl(PIXEL_WIDTH, f.getInteger(MediaFormat.KEY_WIDTH).toLong()) +
                uintEl(PIXEL_HEIGHT, f.getInteger(MediaFormat.KEY_HEIGHT).toLong()))
        } else {
            if (kind == Kind.OPUS) {
                val head = opusHead(f)
                val preSkip = if (head != null && head.size >= 12) (head[10].toInt() and 0xFF) or ((head[11].toInt() and 0xFF) shl 8) else 312
                body += uintEl(CODEC_DELAY, preSkip * 1_000_000_000L / 48000) + uintEl(SEEK_PRE_ROLL, 80_000_000)
            }
            body += element(AUDIO, element(SAMPLING_FREQUENCY, float64(f.getInteger(MediaFormat.KEY_SAMPLE_RATE).toDouble())) +
                uintEl(CHANNELS, f.getInteger(MediaFormat.KEY_CHANNEL_COUNT).toLong()))
        }
        return element(TRACK_ENTRY, body)
    }

    private fun csd(f: MediaFormat, k: String): ByteArray? =
        f.getByteBuffer(k)?.let { b -> ByteArray(b.remaining()).also { b.duplicate().get(it) } }

    fun codecPrivate(f: MediaFormat, kind: Kind): ByteArray? = when (kind) {
        Kind.AVC -> {
            val nals = listOfNotNull(csd(f, "csd-0"), csd(f, "csd-1")).flatMap { annexB(it) }
            avcC(nals.first { (it[0].toInt() and 0x1F) == 7 }, nals.first { (it[0].toInt() and 0x1F) == 8 })
        }
        Kind.HEVC -> hvcC(listOfNotNull(csd(f, "csd-0"), csd(f, "csd-1"), csd(f, "csd-2")).flatMap { annexB(it) })
        Kind.AV1 -> csd(f, "csd-0")?.takeIf { it.isNotEmpty() && (it[0].toInt() and 0xFF) == 0x81 }
            ?: byteArrayOf(0x81.toByte(), 0, 0x0C, 0)
        Kind.AAC, Kind.FLAC -> csd(f, "csd-0")
        Kind.OPUS -> opusHead(f)
        Kind.VORBIS -> {
            val ident = csd(f, "csd-0")!!
            val setup = csd(f, "csd-1")!!
            val comment = byteArrayOf(3) + "vorbis".toByteArray() + ByteArray(4) + ByteArray(4) + byteArrayOf(1)
            xiphLace(listOf(ident, comment, setup))
        }
        else -> null
    }

    /** OpusHead from csd-0: raw ("OpusHead…") or wrapped by Android's encoder ("AOPUSHDR" + size + head). */
    fun opusHead(f: MediaFormat): ByteArray? = csd(f, "csd-0")?.let { unwrapOpusHead(it) }

    fun unwrapOpusHead(c: ByteArray): ByteArray {
        val marker = "OpusHead".toByteArray()
        val at = indexOf(c, marker)
        if (at < 0) return c
        if (at >= 16 && String(c, 0, 8, Charsets.US_ASCII) == "AOPUSHDR") {
            val len = ByteBuffer.wrap(c, 8, 8).order(java.nio.ByteOrder.LITTLE_ENDIAN).long.toInt()
            return c.copyOfRange(at, minOf(c.size, at + len))
        }
        return c.copyOfRange(at, c.size)
    }

    private fun xiphLace(parts: List<ByteArray>): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(parts.size - 1)
        for (p in parts.dropLast(1)) {
            var n = p.size
            while (n >= 255) { out.write(255); n -= 255 }
            out.write(n)
        }
        parts.forEach { out.write(it) }
        return out.toByteArray()
    }

    private fun indexOf(a: ByteArray, b: ByteArray): Int {
        outer@ for (i in 0..a.size - b.size) {
            for (j in b.indices) if (a[i + j] != b[j]) continue@outer
            return i
        }
        return -1
    }

    // ------------------------------------------------------------------ video bitstreams
    /** NAL units of an Annex-B stream (start codes 00 00 01 / 00 00 00 01 removed). */
    fun annexB(b: ByteArray): List<ByteArray> {
        val starts = ArrayList<Pair<Int, Int>>()          // (start code position, payload start)
        var i = 0
        while (i + 2 < b.size) {
            if (b[i].toInt() == 0 && b[i + 1].toInt() == 0 && b[i + 2].toInt() == 1) {
                val at = if (i > 0 && b[i - 1].toInt() == 0) i - 1 else i
                starts += at to i + 3
                i += 3
            } else i++
        }
        if (starts.isEmpty()) return listOf(b)
        return starts.mapIndexed { k, (_, payload) ->
            val end = if (k + 1 < starts.size) starts[k + 1].first else b.size
            b.copyOfRange(payload, end)
        }.filter { it.isNotEmpty() }
    }

    /** Annex-B → 4-byte big-endian lengths (what avcC / hvcC with lengthSizeMinusOne = 3 mean). */
    fun lengthPrefixed(b: ByteArray): ByteArray {
        val nals = annexB(b)
        if (nals.size == 1 && nals[0] === b) return b           // already length-prefixed
        val out = ByteArrayOutputStream(b.size + 8)
        for (n in nals) {
            out.write(ByteBuffer.allocate(4).putInt(n.size).array())
            out.write(n)
        }
        return out.toByteArray()
    }

    /** AV1: temporal delimiter (type 2) and padding (type 15) OBUs are not stored in MKV. */
    fun withoutTemporalDelimiters(b: ByteArray): ByteArray {
        val out = ByteArrayOutputStream(b.size)
        var p = 0
        while (p < b.size) {
            val header = b[p].toInt() and 0xFF
            val type = (header shr 3) and 0x0F
            val ext = header and 0x04 != 0
            val hasSize = header and 0x02 != 0
            var q = p + 1 + if (ext) 1 else 0
            if (!hasSize) {                              // last OBU without a size: the rest
                if (type != 2 && type != 15) out.write(b, p, b.size - p)
                break
            }
            var size = 0L
            var shift = 0
            while (true) {
                val byte = b[q++].toInt() and 0xFF
                size = size or ((byte and 0x7F).toLong() shl shift)
                if (byte and 0x80 == 0) break
                shift += 7
            }
            val end = (q + size).toInt()
            if (type != 2 && type != 15) out.write(b, p, end - p)
            p = end
        }
        return out.toByteArray()
    }

    fun frameData(kind: Kind, raw: ByteArray): ByteArray = when (kind) {
        Kind.AVC, Kind.HEVC -> lengthPrefixed(raw)
        Kind.AV1 -> withoutTemporalDelimiters(raw)
        else -> raw
    }

    /** RBSP of a NAL unit payload: emulation-prevention bytes (00 00 03) removed. */
    fun unescape(b: ByteArray, from: Int): ByteArray {
        val out = ByteArrayOutputStream(b.size)
        var zeros = 0
        for (i in from until b.size) {
            val v = b[i].toInt() and 0xFF
            if (zeros >= 2 && v == 3) { zeros = 0; continue }
            out.write(v)
            zeros = if (v == 0) zeros + 1 else 0
        }
        return out.toByteArray()
    }

    fun avcC(sps: ByteArray, pps: ByteArray): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(byteArrayOf(1, sps[1], sps[2], sps[3], 0xFF.toByte(), 0xE1.toByte()))
        out.write(byteArrayOf((sps.size shr 8).toByte(), sps.size.toByte())); out.write(sps)
        out.write(1)
        out.write(byteArrayOf((pps.size shr 8).toByte(), pps.size.toByte())); out.write(pps)
        val profile = sps[1].toInt() and 0xFF
        if (profile in setOf(100, 110, 122, 144)) {      // High profiles: 4:2:0, 8-bit, no SPS ext
            out.write(byteArrayOf(0xFD.toByte(), 0xF8.toByte(), 0xF8.toByte(), 0))
        }
        return out.toByteArray()
    }

    /**
     * HEVCDecoderConfigurationRecord from VPS / SPS / PPS. Profile, tier, level and the flags come
     * from the SPS's profile_tier_level (bytes 1–12 of its RBSP); the encoders here write 4:2:0
     * 8-bit (frames come through the GPU), which is what the chroma / depth fields say.
     */
    fun hvcC(nals: List<ByteArray>): ByteArray {
        fun type(n: ByteArray) = (n[0].toInt() shr 1) and 0x3F
        val sps = nals.first { type(it) == 33 }
        val rbsp = unescape(sps, 2)
        val maxSubLayersMinus1 = (rbsp[0].toInt() shr 1) and 0x07
        val nested = rbsp[0].toInt() and 0x01
        val ptl = rbsp.copyOfRange(1, 13)
        val out = ByteArrayOutputStream()
        out.write(1)
        out.write(ptl)                                       // profile .. constraint flags .. level
        out.write(byteArrayOf(0xF0.toByte(), 0x00, 0xFC.toByte(), 0xFD.toByte(), 0xF8.toByte(), 0xF8.toByte(), 0, 0))
        out.write(((maxSubLayersMinus1 + 1) shl 3) or (nested shl 2) or 0x03)
        val arrays = listOf(32, 33, 34).map { t -> t to nals.filter { type(it) == t } }.filter { it.second.isNotEmpty() }
        out.write(arrays.size)
        for ((t, list) in arrays) {
            out.write(0x80 or t)
            out.write(byteArrayOf((list.size shr 8).toByte(), list.size.toByte()))
            for (n in list) {
                out.write(byteArrayOf((n.size shr 8).toByte(), n.size.toByte()))
                out.write(n)
            }
        }
        return out.toByteArray()
    }

    // ------------------------------------------------------------------ blocks, cues, seek head
    fun simpleBlock(track: Int, relMs: Int, key: Boolean, data: ByteArray): ByteArray {
        val head = size(track.toLong()) + byteArrayOf((relMs shr 8).toByte(), relMs.toByte(),
            (if (key) 0x80 else 0).toByte())
        return element(SIMPLE_BLOCK, head + data)
    }

    fun cues(points: List<Pair<Long, Long>>, track: Int): ByteArray {
        val body = ByteArrayOutputStream()
        for ((ms, pos) in points) {
            body.write(element(CUE_POINT, uintEl(CUE_TIME, ms) +
                element(CUE_TRACK_POSITIONS, uintEl(CUE_TRACK, track.toLong()) + uintEl(CUE_CLUSTER_POSITION, pos))))
        }
        return element(CUES, body.toByteArray())
    }

    fun seekHead(entries: List<Pair<Long, Long>>): ByteArray = element(SEEK_HEAD,
        entries.fold(ByteArray(0)) { acc, (target, pos) ->
            acc + element(SEEK, element(SEEK_ID, id(target)) + uintEl(SEEK_POSITION, pos))
        })
}
