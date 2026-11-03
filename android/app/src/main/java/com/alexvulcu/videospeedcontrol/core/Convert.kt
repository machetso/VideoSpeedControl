package com.alexvulcu.videospeedcontrol.core

import org.json.JSONObject

/**
 * "Convert videos" (user request 2026-11-03, desktop: vsc/core/convert.py): re-encode many files
 * with one codec and quality and nothing else changed – every frame once at the file's own
 * frame rate, source size, sound kept – into MP4 in Movies/VideoSpeedControl/Converted/.
 * Made for old collections (AVI / DivX / Xvid, read through [Extractor]) as well as phone clips.
 */
object Convert {
    const val FOLDER = "Movies/VideoSpeedControl/Converted/"

    /** Codecs offered, default first (user choice: AV1). AV1 = [VideoCodec.AV1_FAST], see [pickCodec]. */
    val CODECS = listOf(VideoCodec.AV1_FAST, VideoCodec.HEVC, VideoCodec.AVC)

    /** Bitrate floor for High; scaled with the quality level (old 368×208 DivX ≈ 0.5 Mbit/s). */
    private const val MIN_BITRATE_HIGH = 200_000

    val VIDEO_EXTENSIONS = setOf(
        "mp4", "m4v", "mov", "mkv", "webm", "avi", "divx", "xvid", "wmv", "asf", "flv", "mpg", "mpeg",
        "mpe", "m2v", "vob", "ts", "mts", "m2ts", "mxf", "3gp", "3g2", "ogv", "dv", "360", "lrv",
    )

    fun codecLabel(codec: VideoCodec): String = when (codec) {
        VideoCodec.AV1_FAST, VideoCodec.AV1_BEST -> "AV1"
        else -> codec.short
    }

    fun isVideoName(name: String) = name.substringAfterLast('.', "").lowercase() in VIDEO_EXTENSIONS

    /** File name without its video extensions: "Clip.avi.MP4.AVI" → "Clip" (like the desktop). */
    fun cleanStem(name: String): String {
        var n = name
        while (true) {
            val dot = n.lastIndexOf('.')
            if (dot <= 0 || n.substring(dot + 1).lowercase() !in VIDEO_EXTENSIONS) break
            n = n.substring(0, dot)
        }
        n = n.trim(' ', '.')
        return n.ifEmpty { name.substringBeforeLast('.').ifEmpty { "video" } }
    }

    /** "2 - x" before "10 - x", case-insensitive. */
    val naturalOrder: Comparator<String> = Comparator { a, b ->
        val ta = Regex("""\d+|\D+""").findAll(a.lowercase()).map { it.value }.toList()
        val tb = Regex("""\d+|\D+""").findAll(b.lowercase()).map { it.value }.toList()
        for (i in 0 until minOf(ta.size, tb.size)) {
            val x = ta[i]; val y = tb[i]
            val c = if (x[0].isDigit() && y[0].isDigit()) x.toBigInteger().compareTo(y.toBigInteger()) else x.compareTo(y)
            if (c != 0) return@Comparator c
        }
        ta.size - tb.size
    }

    /**
     * The encoder to use for a [width]×[height] video at [fps]: [preferred] if this phone can,
     * else the next one. AV1: the AV1 chip, else the software AV1 encoder at its fastest setting
     * (the Pixel's chip needs ≥ 256 px – old 368×208 videos don't fit; small sizes are quick in
     * software), else HEVC, else H.264. Second value: use the software encoder's fastest setting.
     */
    fun pickCodec(preferred: VideoCodec, width: Int, height: Int, fps: Double,
                  supports: (VideoCodec) -> Boolean = { Encoders.supports(it, width, height, fps) }): Pair<VideoCodec, Boolean> {
        val order = when (preferred) {
            VideoCodec.AV1_FAST -> listOf(VideoCodec.AV1_FAST to false, VideoCodec.AV1_BEST to true)
            VideoCodec.AV1_BEST -> listOf(VideoCodec.AV1_BEST to false)
            VideoCodec.HEVC -> listOf(VideoCodec.HEVC to false)
            VideoCodec.AVC -> listOf(VideoCodec.AVC to false)
        } + listOf(VideoCodec.HEVC to false, VideoCodec.AVC to false)
        return order.firstOrNull { supports(it.first) } ?: (VideoCodec.AVC to false)
    }

    fun minBitrate(quality: Quality): Int =
        (MIN_BITRATE_HIGH * quality.bitsPerPixel / Quality.HIGH.bitsPerPixel).toInt()

    /** Every frame once at the file's rate, source size, the codec this phone can use. */
    fun job(info: ClipInfo, codec: VideoCodec, quality: Quality,
            supports: ((VideoCodec, Int, Int, Double) -> Boolean)? = null): ReencodeJob {
        val plain = ReencodeJob(info, info.fps, null, Trim(), emptyList(), codec, null, quality)
        val (w, h) = plain.outputSize()
        val fps = info.fps.toDouble()
        val (use, fastest) = if (supports == null) pickCodec(codec, w, h, fps)
            else pickCodec(codec, w, h, fps) { supports(it, w, h, fps) }
        return plain.copy(codec = use, fastest = fastest, minBitrate = minBitrate(quality))
    }

    /** The export task for one video (sound only if it has some). */
    fun task(id: Long, info: ClipInfo, codec: VideoCodec, quality: Quality, sound: Boolean): ExportTask {
        val settings = Treatment.Settings(mode = Treatment.Mode.REENCODE, fps = info.fps, codec = codec,
            quality = quality, sound = sound && info.audio != null, convert = true)
        val data = Treatment.Data(info.name, info.sizeBytes, "", info.frames.count, settings, Trim(), emptyList(),
            ui = JSONObject())
        return ExportTask(id, info.uri, data, info.videoMime)
    }
}
