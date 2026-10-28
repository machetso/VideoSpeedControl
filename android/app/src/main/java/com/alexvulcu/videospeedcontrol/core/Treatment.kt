package com.alexvulcu.videospeedcontrol.core

import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream
import java.security.MessageDigest

/**
 * Clip speed treatment files (.cst) – the desktop's `vsc/core/treatment.py` format, so a clip
 * prepared on the phone can be finished on the PC and vice versa.
 *
 * JSON, fractions as strings ("240000/1001"). A treatment belongs to exactly one video: it stores
 * a fingerprint (SHA-256 over the size and the first / middle / last MiB) and the frame count,
 * and only loads onto a file with the same fingerprint and frame count – whatever its name.
 */
object Treatment {
    const val SUFFIX = ".cst"
    const val FORMAT = "VideoSpeedControl clip speed treatment"
    const val VERSION = 1
    private const val CHUNK = 1 shl 20

    /** Desktop quality levels (formats.QUALITY_LEVELS) and the codec values (QUALITY_VALUES). */
    private val QUALITY_VALUES = mapOf("x264" to listOf(14, 18, 23, 28, 34), "x265" to listOf(16, 20, 25, 30, 35))

    class TreatmentError(message: String) : Exception(message)

    /** Export mode and settings as the Android UI holds them. */
    enum class Mode { LOSSLESS, SMART, REENCODE }

    data class Settings(
        val mode: Mode = Mode.LOSSLESS,
        val fps: Rational = Rational.of(25),
        val speed: Rational? = null,               // re-encode without sections; null = every frame once
        val codec: VideoCodec = VideoCodec.HEVC,
        val quality: Quality = Quality.HIGH,
        val shortSide: Int? = null,
        val sound: Boolean = true,
        val smartAuto: Boolean = true,
        val size: Pair<Int, Int>? = null,          // re-encode output size when shortSide is set (desktop fit_box)
    )

    data class Data(
        val sourceName: String,
        val sourceSize: Long,
        val fingerprint: String,
        val frames: Int,
        val settings: Settings,
        val trim: Trim,
        val segments: List<Segment>,
        val sourcePath: String = "",
        val ui: JSONObject = JSONObject(),
    ) {
        /** Throws unless the file with [size], [fingerprint] and [frames] is this treatment's video. */
        fun check(name: String, size: Long, fingerprint: String, frames: Int) {
            if (size != sourceSize || fingerprint != this.fingerprint) {
                throw TreatmentError("This treatment belongs to another video: $sourceName " +
                    "(${"%,d".format(sourceSize)} bytes, ${this.frames} frames).\n$name is a different file, " +
                    "so its sections and trim would not fit.")
            }
            if (frames != this.frames) {
                throw TreatmentError("$name has $frames frames, the treatment was made for ${this.frames} frames.")
            }
        }
    }

    /**
     * Identity of a video file's content: SHA-256 over str(size), then the first, middle and last
     * MiB (desktop `treatment.fingerprint`). [open] returns a fresh stream of the file each time.
     */
    fun fingerprint(size: Long, open: () -> InputStream): String {
        val md = MessageDigest.getInstance("SHA-256")
        md.update(size.toString().toByteArray())
        val offsets = sortedSetOf(0L, maxOf(0L, size / 2 - CHUNK / 2), maxOf(0L, size - CHUNK))
        val buf = ByteArray(CHUNK)
        for (offset in offsets) {
            open().use { input ->
                var skipped = 0L
                while (skipped < offset) {
                    val n = input.skip(offset - skipped)
                    if (n <= 0) { if (input.read() < 0) break; skipped++ } else skipped += n
                }
                var got = 0
                while (got < CHUNK) {
                    val n = input.read(buf, got, CHUNK - got)
                    if (n < 0) break
                    got += n
                }
                md.update(buf, 0, got)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    // ------------------------------------------------------------------ save

    fun toJson(d: Data, sourceCodec: String): String {
        val s = d.settings
        val desktopCodec = when (s.mode) {
            Mode.LOSSLESS -> "copy"
            Mode.SMART -> if (sourceCodec == android.media.MediaFormat.MIMETYPE_VIDEO_AVC) "x264" else "x265"
            Mode.REENCODE -> if (s.codec == VideoCodec.AVC) "x264" else "x265"
        }
        val quality = if (s.mode == Mode.LOSSLESS) null else QUALITY_VALUES.getValue(desktopCodec)[
            when (s.quality) { Quality.VERY_HIGH -> 0; Quality.HIGH -> 1; Quality.GOOD -> 2 }]
        val settings = JSONObject().apply {
            put("fps", s.fps.toString())
            put("speed", if (s.mode == Mode.REENCODE && s.speed != null) s.speed.toString() else JSONObject.NULL)
            put("codec", desktopCodec)
            put("container", JSONObject.NULL)
            put("profile", JSONObject.NULL)
            put("preset", JSONObject.NULL)
            put("quality", quality ?: JSONObject.NULL)
            put("chroma", JSONObject.NULL)
            put("depth", JSONObject.NULL)
            val box = s.size?.takeIf { s.mode == Mode.REENCODE && s.shortSide != null }
            put("resize", if (box != null) "fit_box" else "source")
            put("width", box?.first ?: JSONObject.NULL)
            put("height", box?.second ?: JSONObject.NULL)
            put("fit", "pad")
            put("scaler", "lanczos")
            put("interpolation", "blend")
            put("smart", s.mode == Mode.SMART)
            put("audio", s.sound)
        }
        val ui = JSONObject(d.ui.toString()).apply {
            put("android", JSONObject().apply {
                put("mode", s.mode.name.lowercase())
                put("codec", s.codec.name)
                put("quality", s.quality.name)
                put("short_side", s.shortSide ?: JSONObject.NULL)
                put("smart_auto", s.smartAuto)
            })
        }
        val root = JSONObject().apply {
            put("format", FORMAT)
            put("version", VERSION)
            put("source", JSONObject().apply {
                put("name", d.sourceName)
                put("path", d.sourcePath)
                put("size", d.sourceSize)
                put("fingerprint", d.fingerprint)
                put("frames", d.frames)
            })
            put("settings", settings)
            put("ui", ui)
            put("trim", JSONObject().apply {
                put("start", d.trim.start)
                put("end", d.trim.end ?: JSONObject.NULL)
            })
            put("sections", JSONArray().apply {
                for (seg in d.segments) put(JSONObject().apply {
                    put("start", seg.start)
                    put("end", seg.end)
                    put("fps", seg.fps.toString())
                    put("reencode", seg.reencode)
                    put("out_fps", seg.outFps?.toString() ?: JSONObject.NULL)
                })
            })
        }
        return root.toString(2) + "\n"
    }

    // ------------------------------------------------------------------ load

    fun fromJson(text: String, fileName: String): Data {
        try {
            val root = JSONObject(text)
            if (root.optString("format") != FORMAT) throw TreatmentError("$fileName is not a clip speed treatment file.")
            if (root.optInt("version", 0) > VERSION) {
                throw TreatmentError("$fileName was saved by a newer version of VideoSpeedControl.")
            }
            val src = root.getJSONObject("source")
            val st = root.getJSONObject("settings")
            val ui = root.optJSONObject("ui") ?: JSONObject()
            val android = ui.optJSONObject("android")
            val codecKey = st.optString("codec", "copy")
            val smart = st.optBoolean("smart", false)
            val mode = when {
                smart -> Mode.SMART
                codecKey == "copy" -> Mode.LOSSLESS
                else -> Mode.REENCODE
            }
            // desktop codecs: x264 / h264_* → H.264, everything else (x265, hevc_*, prores …) → HEVC
            val codec = android?.optString("codec")?.let { runCatching { VideoCodec.valueOf(it) }.getOrNull() }
                ?: if (codecKey == "x264" || codecKey.startsWith("h264")) VideoCodec.AVC else VideoCodec.HEVC
            val quality = android?.optString("quality")?.let { runCatching { Quality.valueOf(it) }.getOrNull() }
                ?: st.optNullInt("quality")?.let { q ->
                    when (QUALITY_VALUES[codecKey]?.indexOf(q)) { 0 -> Quality.VERY_HIGH; 1, -1, null -> Quality.HIGH; else -> Quality.GOOD }
                } ?: Quality.HIGH
            val box = if (st.optString("resize") != "source") st.optNullInt("width")?.let { w ->
                st.optNullInt("height")?.let { h -> w to h } } else null
            val shortSide = android?.optNullInt("short_side")
                ?: if (st.optString("resize") != "source") {
                    listOfNotNull(st.optNullInt("width"), st.optNullInt("height")).minOrNull()
                } else null
            val settings = Settings(
                mode = mode,
                fps = Rational.parse(st.getString("fps")),
                speed = st.optNullString("speed")?.let(Rational::parse),
                codec = codec,
                quality = quality,
                shortSide = shortSide,
                sound = st.optBoolean("audio", true),
                smartAuto = android?.optBoolean("smart_auto", true) ?: true,
                size = box,
            )
            val trimJ = root.getJSONObject("trim")
            val trim = Trim(trimJ.getInt("start"), trimJ.optNullInt("end"))
            val secs = root.getJSONArray("sections")
            val segments = (0 until secs.length()).map { i ->
                val o = secs.getJSONObject(i)
                Segment(o.getInt("start"), o.getInt("end"), Rational.parse(o.getString("fps")),
                    o.optBoolean("reencode", false), o.optNullString("out_fps")?.let(Rational::parse))
            }
            return Data(src.getString("name"), src.getLong("size"), src.getString("fingerprint"),
                src.getInt("frames"), settings, trim, segments, src.optString("path", ""), ui)
        } catch (e: TreatmentError) {
            throw e
        } catch (e: Exception) {
            throw TreatmentError("$fileName is damaged or incomplete (${e.message}).")
        }
    }

    private fun JSONObject.optNullInt(key: String): Int? = if (isNull(key) || !has(key)) null else getInt(key)
    private fun JSONObject.optNullString(key: String): String? =
        if (isNull(key) || !has(key)) null else get(key).toString()
}
