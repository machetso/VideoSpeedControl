package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.OpenableColumns

/** Recorded faster than it plays above this ratio of capture fps to file fps (as desktop). */
const val SLOWMO_MIN = 1.5

/**
 * Presentation times (µs, display order) of every video frame plus keyframe indices.
 * Built from sample headers only (no decoding) – the Android counterpart of `probe.FrameMap`.
 */
class FrameMap(val ptsUs: LongArray, val keyframes: IntArray) {
    val count get() = ptsUs.size

    fun keyframeAtOrBefore(frame: Int): Int {
        var i = keyframes.binarySearch(frame)
        if (i < 0) i = -i - 2
        return keyframes[maxOf(i, 0)]
    }

    /** First keyframe strictly after [frame], or the frame count (end of clip). */
    fun keyframeAfter(frame: Int): Int {
        var i = keyframes.binarySearch(frame)
        i = if (i < 0) -i - 1 else i + 1
        return if (i < keyframes.size) keyframes[i] else count
    }

    /** Nearest keyframe for an in-point. */
    fun snapIn(frame: Int): Int {
        val before = keyframeAtOrBefore(frame)
        val after = keyframeAfter(frame)
        return if (after < count && after - frame < frame - before) after else before
    }

    /** Nearest GOP boundary (exclusive end) for an out-point. */
    fun snapOut(frame: Int): Int =
        (keyframes.drop(1) + count).minBy { kotlin.math.abs(it - frame) }

    /** Index of the frame with presentation time [us] (exact match), or -1. */
    fun indexOf(us: Long): Int = ptsUs.binarySearch(us).let { if (it < 0) -1 else it }

    /**
     * Presentation times in seconds, display order, plus the end of the last frame.
     * MediaExtractor rounds to whole µs; when every frame sits on the [fps] grid within that
     * rounding, the exact grid times are used (otherwise a retime would scale the rounding into
     * visible-in-ffprobe jitter). Real timing variation (phones) is kept as it is.
     */
    fun exactTimes(fps: Rational): Pair<Array<Rational>, Rational> {
        val million = Rational.of(1_000_000)
        val p0 = ptsUs.first()
        val step = 1e6 / fps.toDouble()
        val onGrid = ptsUs.indices.all { kotlin.math.abs(ptsUs[it] - p0 - it * step) <= 1.0 }
        return if (onGrid) {
            val t0 = Rational.of(p0) / million
            Array(count) { t0 + Rational.of(it.toLong()) / fps } to t0 + Rational.of(count.toLong()) / fps
        } else {
            val lastLen = if (count > 1) ptsUs[count - 1] - ptsUs[count - 2] else 1L
            Array(count) { Rational.of(ptsUs[it]) / million } to Rational.of(ptsUs.last() + lastLen) / million
        }
    }

    /** (min, max) distance between consecutive frames in µs, for VFR detection. */
    fun frameIntervals(): Pair<Long, Long> {
        if (count < 2) return 0L to 0L
        var lo = Long.MAX_VALUE; var hi = Long.MIN_VALUE
        for (i in 1 until count) {
            val d = ptsUs[i] - ptsUs[i - 1]
            if (d < lo) lo = d
            if (d > hi) hi = d
        }
        return lo to hi
    }
}

data class ClipInfo(
    val uri: Uri,
    val name: String,
    val sizeBytes: Long,
    val videoMime: String,          // "video/hevc", "video/avc", …
    val width: Int,
    val height: Int,
    val rotation: Int,
    val durationUs: Long,
    val fps: Rational,              // file frame rate (timestamps / seeking use this)
    val captureFps: Rational?,      // phones: rate the sensor recorded at
    val bitrate: Int?,
    val hdr: String?,               // "HLG" / "PQ (HDR10)" / null = SDR
    val audio: String?,             // first audio track, e.g. "AAC stereo 48 kHz"
    val audioRate: Int?,
    val recorded: java.time.Instant?,  // container creation time
    val frames: FrameMap,
    val videoProfile: Int? = null,  // MediaFormat KEY_PROFILE (decoder check), if the file says
) {
    /** > 1 if the file is already slowed down (recorded faster than it plays). */
    val slowmoFactor: Double?
        get() = captureFps?.let { (it / fps).toDouble() }?.takeIf { it >= SLOWMO_MIN }

    /** Frames per second of real time: capture rate for phone slow-mo, else the file rate. */
    val realFps: Rational get() = if (slowmoFactor != null) captureFps!! else fps

    val displayWidth get() = if (rotation % 180 != 0) height else width
    val displayHeight get() = if (rotation % 180 != 0) width else height

    val codecName: String
        get() = when (videoMime) {
            MediaFormat.MIMETYPE_VIDEO_AVC -> "H.264"
            MediaFormat.MIMETYPE_VIDEO_HEVC -> "HEVC"
            MediaFormat.MIMETYPE_VIDEO_AV1 -> "AV1"
            MediaFormat.MIMETYPE_VIDEO_VP9 -> "VP9"
            MediaFormat.MIMETYPE_VIDEO_VP8 -> "VP8"
            MediaFormat.MIMETYPE_VIDEO_MPEG4 -> "MPEG-4 Part 2"     // DivX / Xvid
            MediaFormat.MIMETYPE_VIDEO_MPEG2 -> "MPEG-2"
            MediaFormat.MIMETYPE_VIDEO_H263 -> "H.263"
            else -> videoMime.removePrefix("video/")
        }

    /** Average keyframe interval in frames. */
    val keyframeInterval: Double get() = frames.count.toDouble() / maxOf(1, frames.keyframes.size)
}

object Probe {
    private val STANDARD_RATES = listOf(
        "10", "12", "25/2", "15", "20",          // old videos (AVI / DivX, early phones, 2026-11-03)
        "24000/1001", "24", "25", "30000/1001", "30", "48", "50", "60000/1001", "60",
        "90", "100", "120", "240", "480", "960",
    ).map(Rational::parse)

    fun probe(context: Context, uri: Uri): ClipInfo {
        val (name, size) = nameAndSize(context, uri)
        val ex = Extractor()
        try {
            ex.setDataSource(context, uri, null)
            var video = -1
            var audioFmt: MediaFormat? = null
            for (i in 0 until ex.trackCount) {
                val mime = ex.getTrackFormat(i).getString(MediaFormat.KEY_MIME) ?: continue
                if (video < 0 && mime.startsWith("video/")) video = i
                if (audioFmt == null && mime.startsWith("audio/")) audioFmt = ex.getTrackFormat(i)
            }
            require(video >= 0) { "$name has no video track." }
            val fmt = ex.getTrackFormat(video)
            val frames = scanFrames(ex, video)
            require(frames.count > 0) { "$name contains no video frames." }

            // Android's metadata reader can't open every file Media3 reads (AVI) – then without it
            val meta = runCatching { MediaMetadataRetriever().apply { setDataSource(context, uri) } }.getOrNull()
            try {
                val fileFps = fileFps(frames, fmt)
                // own mdta reader first (text or float, like the desktop), then Android's
                val capture = (runCatching { Mp4Meta.tags(context, uri)["com.android.capture.fps"] }.getOrNull()
                    ?: meta?.extractMetadata(MediaMetadataRetriever.METADATA_KEY_CAPTURE_FRAMERATE))
                    ?.trim()?.toDoubleOrNull()?.takeIf { it > 0 }?.let { Rational.fromDouble(it) }
                val durationUs = if (fmt.containsKey(MediaFormat.KEY_DURATION))
                    fmt.getLong(MediaFormat.KEY_DURATION) else frames.ptsUs.last() - frames.ptsUs.first()
                return ClipInfo(
                    uri = uri, name = name, sizeBytes = size,
                    videoMime = fmt.getString(MediaFormat.KEY_MIME)!!,
                    width = fmt.getInteger(MediaFormat.KEY_WIDTH),
                    height = fmt.getInteger(MediaFormat.KEY_HEIGHT),
                    rotation = meta?.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)
                        ?.toIntOrNull() ?: fmt.intOrNull(MediaFormat.KEY_ROTATION) ?: 0,
                    durationUs = durationUs,
                    fps = fileFps,
                    captureFps = capture,
                    bitrate = meta?.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toIntOrNull()
                        ?: size.takeIf { it > 0 && durationUs > 0 }?.let { (it * 8e6 / durationUs).toInt() },
                    hdr = when (fmt.intOrNull(MediaFormat.KEY_COLOR_TRANSFER)) {
                        MediaFormat.COLOR_TRANSFER_HLG -> "HLG"
                        MediaFormat.COLOR_TRANSFER_ST2084 -> "PQ (HDR10)"
                        else -> null
                    },
                    audio = audioFmt?.let(::describeAudio),
                    audioRate = audioFmt?.intOrNull(MediaFormat.KEY_SAMPLE_RATE),
                    recorded = parseDate(meta?.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DATE)),
                    frames = frames,
                    videoProfile = fmt.intOrNull(MediaFormat.KEY_PROFILE),
                )
            } finally {
                meta?.release()
            }
        } finally {
            ex.release()
        }
    }

    /** Walk all samples of the track without reading their data. */
    fun scanFrames(ex: Extractor, track: Int): FrameMap {
        ex.selectTrack(track)
        ex.seekTo(0, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
        val samples = ArrayList<Pair<Long, Boolean>>()
        while (true) {
            val t = ex.sampleTime
            if (t < 0) break
            samples += t to (ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0)
            if (!ex.advance()) break
        }
        ex.unselectTrack(track)
        samples.sortBy { it.first }
        val keys = samples.indices.filter { samples[it].second }.toIntArray()
        return FrameMap(
            LongArray(samples.size) { samples[it].first },
            if (keys.isEmpty() && samples.isNotEmpty()) intArrayOf(0) else keys,
        )
    }

    /**
     * Nominal rate from the frame timestamps (MediaFormat's KEY_FRAME_RATE is often missing or
     * rounded): median frame interval, snapped to a standard rate when within 0.5 %.
     */
    private fun fileFps(frames: FrameMap, fmt: MediaFormat): Rational {
        val p = frames.ptsUs
        if (p.size >= 2) {
            val d = LongArray(p.size - 1) { p[it + 1] - p[it] }.sorted()
            val median = d[d.size / 2].takeIf { it > 0 }
            if (median != null) {
                val avg = (p.size - 1) * 1_000_000.0 / (p.last() - p.first())
                val est = if (kotlin.math.abs(avg * median / 1e6 - 1) < 0.02) avg else 1e6 / median
                fun standard(e: Double) = STANDARD_RATES.minBy { kotlin.math.abs(it.toDouble() / e - 1) }
                    .takeIf { kotlin.math.abs(it.toDouble() / e - 1) < 0.005 }
                standard(est)?.let { return it }
                // a few dropped frames (AVI) lower the average: the usual frame spacing decides
                standard(1e6 / median)?.let { return it }
                return Rational.fromDouble(est)
            }
        }
        return fmt.intOrNull(MediaFormat.KEY_FRAME_RATE)?.let { Rational.of(it.toLong()) } ?: Rational.of(30)
    }

    private fun describeAudio(f: MediaFormat): String {
        val codec = when (val m = f.getString(MediaFormat.KEY_MIME)) {
            MediaFormat.MIMETYPE_AUDIO_AAC -> "AAC"
            MediaFormat.MIMETYPE_AUDIO_OPUS -> "Opus"
            MediaFormat.MIMETYPE_AUDIO_AC3 -> "AC-3"
            MediaFormat.MIMETYPE_AUDIO_EAC3 -> "E-AC-3"
            MediaFormat.MIMETYPE_AUDIO_MPEG -> "MP3"
            else -> m?.removePrefix("audio/") ?: "?"
        }
        val ch = when (val c = f.intOrNull(MediaFormat.KEY_CHANNEL_COUNT)) {
            1 -> "mono"; 2 -> "stereo"; null -> ""; else -> "$c ch"
        }
        val rate = f.intOrNull(MediaFormat.KEY_SAMPLE_RATE)?.let { "${it / 1000.0} kHz".replace(".0 ", " ") } ?: ""
        return listOf(codec, ch, rate).filter { it.isNotEmpty() }.joinToString(" ")
    }

    private fun nameAndSize(context: Context, uri: Uri): Pair<String, Long> {
        context.contentResolver.query(
            uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null,
        )?.use { c ->
            if (c.moveToFirst()) return (c.getString(0) ?: "clip") to c.getLong(1)
        }
        return (uri.lastPathSegment ?: "clip") to -1L
    }

    /** MediaMetadataRetriever date ("20261025T152738.000Z", UTC) → instant; null if absent / 1904. */
    fun parseDate(text: String?): java.time.Instant? {
        if (text.isNullOrBlank()) return null
        return try {
            val f = java.time.format.DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss[.SSS]'Z'")
                .withZone(java.time.ZoneOffset.UTC)
            java.time.Instant.from(f.parse(text)).takeIf { it.atZone(java.time.ZoneOffset.UTC).year > 1970 }
        } catch (_: java.time.DateTimeException) {
            null
        }
    }

    private fun MediaFormat.intOrNull(key: String) = if (containsKey(key)) getInteger(key) else null
}
