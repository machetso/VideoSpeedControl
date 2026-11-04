package com.alexvulcu.videospeedcontrol.core

import android.media.MediaFormat
import com.alexvulcu.videospeedcontrol.ui.tr
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

    // ------------------------------------------------------------------ pro mode (2026-11-04)

    enum class Rate { LEVEL, KBPS, SMART }
    enum class Goal { IDENTICAL, SMALLER }

    /**
     * What a conversion does (desktop: convert.ConvertSettings). Easy uses codec, quality,
     * rate LEVEL / SMART, goal and audio "default" / "smart" / "none"; pro everything.
     * [audio]: "default" (AAC 192k 48 kHz, as before) | "smart" | "copy" | "aac" | "opus" |
     * "flac" | "none". [fps] / [channels] null = like the source. No own CRF value on the
     * phone: the hardware encoders only take a data rate.
     */
    data class Settings(
        val codec: VideoCodec = VideoCodec.AV1_FAST,
        val container: OutMuxer.Container = OutMuxer.Container.MP4,
        val fps: Rational? = null,
        val rate: Rate = Rate.LEVEL,
        val quality: Quality = Quality.HIGH,
        val kbps: Int = 1000,
        val goal: Goal = Goal.IDENTICAL,
        val audio: String = "default",
        val channels: Int? = null,
        val audioKbps: Int? = null,
    ) {
        val usesRules: Boolean get() = rate == Rate.SMART || audio == "smart"

        fun toJson(): JSONObject = JSONObject().apply {
            put("codec", codec.name); put("container", container.name); put("fps", fps?.toString() ?: JSONObject.NULL)
            put("rate", rate.name); put("quality", quality.name); put("kbps", kbps); put("goal", goal.name)
            put("audio", audio); put("channels", channels ?: JSONObject.NULL); put("audio_kbps", audioKbps ?: JSONObject.NULL)
        }

        companion object {
            val AUDIO_MODES = listOf("default", "smart", "copy", "aac", "opus", "flac", "none")

            fun fromJson(o: JSONObject?): Settings {
                if (o == null) return Settings()
                fun <T> pick(f: () -> T, d: T) = runCatching(f).getOrDefault(d)
                return Settings(
                    codec = pick({ VideoCodec.valueOf(o.getString("codec")) }, VideoCodec.AV1_FAST),
                    container = OutMuxer.Container.of(o.optString("container")),
                    fps = pick({ if (o.isNull("fps")) null else Rational.parse(o.getString("fps")) }, null),
                    rate = pick({ Rate.valueOf(o.getString("rate")) }, Rate.LEVEL),
                    quality = pick({ Quality.valueOf(o.getString("quality")) }, Quality.HIGH),
                    kbps = o.optInt("kbps", 1000),
                    goal = pick({ Goal.valueOf(o.getString("goal")) }, Goal.IDENTICAL),
                    audio = o.optString("audio", "default").takeIf { it in AUDIO_MODES } ?: "default",
                    channels = if (o.isNull("channels") || !o.has("channels")) null else o.optInt("channels"),
                    audioKbps = if (o.isNull("audio_kbps") || !o.has("audio_kbps")) null else o.optInt("audio_kbps"),
                )
            }
        }
    }

    /** Why the sound setting does not fit this file / container (null = it does). */
    fun audioProblem(info: ClipInfo, s: Settings): String? {
        if (info.audio == null || s.audio in setOf("default", "smart", "none")) return null
        if (s.audio == "copy") {
            return if (OutMuxer.canHold(s.container, info.audioMime)) null
            else tr("%s sound can't be copied into %s – choose MKV or another sound codec.",
                audioName(info.audioMime), s.container.name)
        }
        val mime = ConvertAudio.MIMES[s.audio] ?: return null
        return if (OutMuxer.canHold(s.container, mime)) null
        else tr("%s can't be stored in %s.", audioName(mime), s.container.name)
    }

    fun audioName(mime: String?): String = when (mime) {
        MediaFormat.MIMETYPE_AUDIO_AAC -> "AAC"
        MediaFormat.MIMETYPE_AUDIO_MPEG -> "MP3"
        MediaFormat.MIMETYPE_AUDIO_OPUS -> "Opus"
        MediaFormat.MIMETYPE_AUDIO_FLAC -> "FLAC"
        MediaFormat.MIMETYPE_AUDIO_AC3 -> "AC-3"
        MediaFormat.MIMETYPE_AUDIO_EAC3 -> "E-AC-3"
        MediaFormat.MIMETYPE_AUDIO_VORBIS -> "Vorbis"
        null -> "?"
        else -> mime.removePrefix("audio/").uppercase()
    }

    /**
     * Smart settings on the phone (desktop: suggest.py measures with VMAF; the phone has no VMAF).
     * The picture's data rate = the source's × [RATIO] for its codec family and the goal, never
     * below [MIN_BPP] bits per pixel and frame, never above the source. The values are calibrated
     * with the phone's own encoders against VMAF on the desktop (see CLAUDE.md, 2026-11-04).
     */
    data class Suggestion(val videoKbps: Int, val audio: String, val audioKbps: Int?, val channels: Int?,
                          val sizeBytes: Long, val note: String = "")

    /**
     * Share of the source's video data rate the phone's encoders need: family → target codec →
     * (looks identical = VMAF 96, smaller = VMAF 93). Measured 2026-11-04 on the Pixel 10 Pro
     * against a phone-decoded reference (the phone's and FFmpeg's decoders disagree on a few
     * frames of these sources): DivX 368×208 → software AV1 0.88 / 0.51, HEVC 1.18 / 0.75,
     * H.264 1.36 / 0.82; Pixel HEVC 1080p → AV1 chip 0.92 / 0.50, HEVC 1.02 / 0.60, H.264
     * 1.30 / 0.75. H.264 and AV1 sources are interpolated. The phone's real-time encoders are
     * far less efficient than the desktop's (SVT-AV1 kept DivX at ~0.3) – "looks identical"
     * saves little on the phone.
     */
    val RATIO: Map<String, Map<String, Pair<Double, Double>>> = mapOf(
        "old" to mapOf("av1" to (0.88 to 0.51), "hevc" to (1.18 to 0.75), "avc" to (1.36 to 0.82)),
        "avc" to mapOf("av1" to (0.80 to 0.45), "hevc" to (0.92 to 0.55), "avc" to (1.10 to 0.68)),
        "hevc" to mapOf("av1" to (0.92 to 0.50), "hevc" to (1.02 to 0.60), "avc" to (1.30 to 0.75)),
        "av1" to mapOf("av1" to (1.00 to 0.62), "hevc" to (1.25 to 0.75), "avc" to (1.50 to 0.90)),
    )
    val MIN_BPP = mapOf(Goal.IDENTICAL to 0.05, Goal.SMALLER to 0.035)

    private fun target(codec: VideoCodec) = when (codec) {
        VideoCodec.AV1_FAST, VideoCodec.AV1_BEST -> "av1"
        VideoCodec.HEVC -> "hevc"
        VideoCodec.AVC -> "avc"
    }

    /**
     * Android's software AV1 encoder at its fastest setting (videos the AV1 chip can't take)
     * overshoots: measured real ≈ 1.75 × requested + 80 kbit/s (75 → 211, 300 → 604). The rate
     * to ask for so that [realKbps] comes out.
     */
    fun softwareAv1Request(realKbps: Int): Int = maxOf((realKbps * 0.35).toInt(), ((realKbps - 80) / 1.75).toInt(), 30)

    fun family(mime: String): String = when (mime) {
        MediaFormat.MIMETYPE_VIDEO_AVC -> "avc"
        MediaFormat.MIMETYPE_VIDEO_HEVC, MediaFormat.MIMETYPE_VIDEO_VP9 -> "hevc"
        MediaFormat.MIMETYPE_VIDEO_AV1 -> "av1"
        else -> "old"
    }

    fun suggest(info: ClipInfo, codec: VideoCodec, goal: Goal, container: OutMuxer.Container, fps: Rational? = null): Suggestion {
        val (identical, smaller) = RATIO.getValue(family(info.videoMime)).getValue(target(codec))
        val share = if (goal == Goal.IDENTICAL) identical else smaller
        val src = info.videoBitrate ?: 0
        val outFps = (fps ?: info.fps).toDouble()
        val floor = info.displayWidth.toDouble() * info.displayHeight * outFps * MIN_BPP.getValue(goal)
        var bps = maxOf(src * share * outFps / info.fps.toDouble(), floor)
        var note = ""
        if (src > 0 && bps >= src * 0.95) {
            bps = src.toDouble()
            note = tr("No real saving with this codec: it needs about as much data as the original.")
        }
        val kbps = maxOf(50, Math.round(bps / 1000).toInt())
        val (mode, aKbps, ch) = suggestAudio(info, container, goal)
        val soundKbps = if (mode == "copy") (info.audioBitrate ?: 0) / 1000 else aKbps ?: 0
        val size = ((kbps + soundKbps) * 1000L / 8) * info.durationUs / 1_000_000
        return Suggestion(kbps, mode, aKbps, ch, size, note)
    }

    /** Copy if the container holds the source's sound, else AAC with a data rate matched to the source. */
    fun suggestAudio(info: ClipInfo, container: OutMuxer.Container, goal: Goal): Triple<String, Int?, Int?> {
        if (info.audio == null) return Triple("none", null, null)
        if (OutMuxer.canHold(container, info.audioMime)) return Triple("copy", null, info.audioChannels)
        val ch = minOf(info.audioChannels ?: 2, ConvertAudio.MAX_CHANNELS.getValue("aac"))
        val src = (info.audioBitrate ?: 0) / 1000
        val factor = AUDIO_FACTOR[info.audioMime]
        var kbps = if (src > 0 && factor != null) src * factor else (if (goal == Goal.IDENTICAL) 96.0 else 64.0) * ch
        if (goal == Goal.SMALLER) kbps *= 0.8
        val floor = if (ch == 1) 32 else 48 + 24 * (ch - 2)
        return Triple("aac", (Math.round(kbps / 8) * 8).toInt().coerceIn(floor, 512), ch)
    }

    /** AAC data rate relative to the source's, by its codec (desktop: suggest.AUDIO_FACTOR). */
    private val AUDIO_FACTOR = mapOf(MediaFormat.MIMETYPE_AUDIO_MPEG to 0.85, "audio/mpeg-L2" to 0.6,
        MediaFormat.MIMETYPE_AUDIO_AC3 to 0.6, MediaFormat.MIMETYPE_AUDIO_EAC3 to 0.75, "audio/vnd.dts" to 0.5,
        MediaFormat.MIMETYPE_AUDIO_AAC to 1.0, MediaFormat.MIMETYPE_AUDIO_OPUS to 1.25,
        MediaFormat.MIMETYPE_AUDIO_VORBIS to 1.15)

    /** Everything an export of one video with [s] needs (desktop: convert.make_pro_job). */
    class Plan(val job: ReencodeJob, val container: OutMuxer.Container, val audio: ConvertAudio.Plan?,
               val sound: Boolean, val suggestion: Suggestion?)

    fun plan(info: ClipInfo, s: Settings, supports: ((VideoCodec, Int, Int, Double) -> Boolean)? = null): Plan {
        val fps = s.fps ?: info.fps
        val base = job(info, s.codec, s.quality, supports)
        val codec = base.codec
        val container = if (OutMuxer.canHoldVideo(s.container, codec)) s.container else OutMuxer.Container.MP4
        val suggestion = if (s.usesRules) suggest(info, codec, s.goal, container, s.fps) else null
        val bitrate = when (s.rate) {
            Rate.LEVEL -> null
            Rate.KBPS -> s.kbps * 1000
            Rate.SMART -> suggestion!!.videoKbps.let { if (base.fastest) softwareAv1Request(it) else it } * 1000
        }
        val job = base.copy(fps = fps, speedSetting = if (fps == info.fps) null else Rational.ONE,
            bitrateOverride = bitrate)
        val mode = if (s.audio == "smart") suggestion!!.audio else s.audio
        val sound = info.audio != null && mode != "none"
        val audio = when {
            !sound || mode == "default" -> null
            mode == "copy" -> ConvertAudio.Plan("copy")
            else -> {
                val sug = if (s.audio == "smart") suggestion else null
                ConvertAudio.Plan(mode, s.audioKbps ?: sug?.audioKbps, s.channels ?: sug?.channels)
            }
        }
        return Plan(job, container, audio, sound, suggestion)
    }

    /** Pro / smart task (the settings travel in the task, not in a .cst). */
    fun task(id: Long, info: ClipInfo, s: Settings): ExportTask {
        val settings = Treatment.Settings(mode = Treatment.Mode.REENCODE, fps = s.fps ?: info.fps, codec = s.codec,
            quality = s.quality, sound = info.audio != null && s.audio != "none", convert = true, convertSettings = s)
        val data = Treatment.Data(info.name, info.sizeBytes, "", info.frames.count, settings, Trim(), emptyList(),
            ui = JSONObject())
        return ExportTask(id, info.uri, data, info.videoMime)
    }
}
