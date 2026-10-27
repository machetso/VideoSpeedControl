package com.alexvulcu.videospeedcontrol.core

import android.media.MediaFormat
import java.util.Locale

/** Source range in frames: [start, end). end = null means until the end of the clip. */
data class Trim(val start: Int = 0, val end: Int? = null)

/**
 * Timing shared by every export: which source frames, and when each one starts in the output.
 * The sound ([Audio]) only needs this, so it works the same for lossless and re-encoded exports.
 */
interface Timing {
    val info: ClipInfo
    val trim: Trim
    val segments: List<Segment>
    /** Output frame rate (lossless: only used in the file name). */
    val fps: Rational

    val trimEnd: Int get() = trim.end?.let { minOf(it, info.frames.count) } ?: info.frames.count
    val sourceFrameCount: Int get() = maxOf(0, trimEnd - trim.start)

    /** Sections inside the trim range: they replace the global speed. */
    val hasSegments: Boolean get() = segments.any { it.start < trimEnd && it.end > trim.start }

    /** Rate (source frames per output second) outside sections when there are none. */
    val baseRate: Rational

    fun pieces(): List<Piece> =
        if (hasSegments) Segments.pieces(segments, trim.start, trimEnd, info.realFps)
        else Segments.pieces(emptyList(), trim.start, trimEnd, baseRate)

    val outputDuration: Rational get() = Segments.duration(pieces())

    /** Speed relative to real time (average over the output when there are sections). */
    val speed: Rational
        get() {
            val real = Rational.of(sourceFrameCount.toLong()) / info.realFps
            val out = outputDuration
            return if (out == Rational.ZERO) Rational.ONE else real / out
        }

    /** Desktop default pattern "{name}_{speed}x_{fps}fps" (batch.render_name). */
    fun fileStem(): String {
        val stem = info.name.substringBeforeLast('.')
        val name = "${stem}_${LosslessJob.num3(speed.toDouble())}x_${LosslessJob.fpsToken(fps)}fps"
        return name.replace(UNSAFE_NAME, "_").trim(' ', '.').ifEmpty { stem }
    }
}

private val UNSAFE_NAME = Regex("""[<>:"/\\|?*\x00-\x1f]""")

/**
 * One lossless export of a clip – the part of the desktop's `job.Job` that mode A needs.
 * Without sections every frame lasts 1/[fps] (desktop: `-itsscale`); with sections the frames
 * outside them play in real time ([ClipInfo.realFps]) and each section at its own rate.
 */
data class LosslessJob(
    override val info: ClipInfo,
    override val fps: Rational,
    override val trim: Trim = Trim(),
    override val segments: List<Segment> = emptyList(),
) : Timing {
    val frames get() = info.frames
    override val baseRate get() = fps

    /** Why this export can't be done without re-encoding (empty = possible). */
    fun blockers(): List<String> = buildList {
        if (sourceFrameCount <= 0) add("The trim range is empty")
        if (trim.start != 0 && trim.start !in frames.keyframes) add("Trim start is not on a keyframe")
        val end = trim.end
        if (end != null && end < frames.count && end !in frames.keyframes) add("Trim end is not on a keyframe")
        if (Muxing.containerFor(info.videoMime) == null) add("${info.codecName} can't be saved without re-encoding")
    }

    companion object {
        /** Python's f"{v:.3g}" with "." → "_" (0.208 → "0_208", 4.8 → "4_8", 10 → "10"). */
        fun num3(v: Double): String = pyG(v, 3).replace('.', '_')

        fun fpsToken(fps: Rational) = pyG(fps.toDouble(), 5).replace('.', '_')

        /** Python's general format "{:.Ng}" (no trailing zeros, no exponent for normal values). */
        fun pyG(v: Double, digits: Int): String {
            if (v == 0.0) return "0"
            val s = java.math.BigDecimal(v).round(java.math.MathContext(digits)).stripTrailingZeros()
            return if (s.precision() - s.scale() > digits) String.format(Locale.US, "%.${digits - 1}e", v)
            else s.toPlainString()
        }
    }
}

enum class VideoCodec(val label: String, val mime: String, val bitsFactor: Double) {
    HEVC("HEVC (H.265)", MediaFormat.MIMETYPE_VIDEO_HEVC, 1.0),
    AVC("H.264", MediaFormat.MIMETYPE_VIDEO_AVC, 1.5),
}

/** Named quality levels (desktop: QUALITY_LEVELS) as bits per pixel and frame for HEVC. */
enum class Quality(val label: String, val bitsPerPixel: Double) {
    GOOD("Good", 0.06), HIGH("High", 0.10), VERY_HIGH("Very high", 0.16),
}

/**
 * Re-encode (desktop modes B / C / re-encode every frame once): constant output frame rate
 * [fps]. Every output frame shows the source frame current at its time (desktop: `setpts` from
 * the frame number, then `fps=`): slower than the source → frames repeat, faster → dropped.
 * Trim at any frame. [speed] relative to real time; null = every frame once at [fps].
 */
data class ReencodeJob(
    override val info: ClipInfo,
    override val fps: Rational,
    val speedSetting: Rational? = null,
    override val trim: Trim = Trim(),
    override val segments: List<Segment> = emptyList(),
    val codec: VideoCodec = VideoCodec.HEVC,
    /** Short side of the output (e.g. 1080), null = source size. */
    val shortSide: Int? = null,
    val quality: Quality = Quality.HIGH,
) : Timing {
    override val baseRate: Rational get() = speedSetting?.let { info.realFps * it } ?: fps

    val outputFrameCount: Int
        get() = maxOf(1, (outputDuration * fps + Rational.of(1, 2)).floor().toInt())

    /** Output size (display orientation), aspect kept, even numbers. */
    fun outputSize(): Pair<Int, Int> {
        val w = info.displayWidth
        val h = info.displayHeight
        val target = shortSide?.takeIf { it < minOf(w, h) } ?: return even(w.toDouble()) to even(h.toDouble())
        return if (w <= h) even(target.toDouble()) to even(h.toDouble() * target / w)
        else even(w.toDouble() * target / h) to even(target.toDouble())
    }

    val bitrate: Int
        get() {
            val (w, h) = outputSize()
            val bps = w.toDouble() * h * fps.toDouble() * quality.bitsPerPixel * codec.bitsFactor
            return bps.coerceIn(1e6, 200e6).toInt()
        }

    fun blockers(): List<String> = buildList {
        if (sourceFrameCount <= 0) add("The trim range is empty")
    }

    /** Nearest even number (encoders need even sizes): 853.3 → 854. */
    private fun even(v: Double) = maxOf(2, (Math.round(v / 2) * 2).toInt())
}
