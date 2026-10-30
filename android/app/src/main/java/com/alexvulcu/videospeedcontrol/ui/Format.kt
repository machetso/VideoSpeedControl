package com.alexvulcu.videospeedcontrol.ui

import com.alexvulcu.videospeedcontrol.core.LosslessJob
import com.alexvulcu.videospeedcontrol.core.Rational
import java.util.Locale
import kotlin.math.abs
import kotlin.math.round

private val L: Locale get() = I18n.locale
private val DOT: Char get() = if (I18n.german) ',' else '.'

fun fmt(v: Double): String = String.format(L, "%.3g", v).let {
    if ('e' in it) String.format(L, "%.0f", v) else it
}

fun fmtFps(v: Double): String = String.format(L, "%.3f", v).trimEnd('0').trimEnd(DOT)

fun clock(seconds: Double): String {
    val s = round(seconds).toLong()
    return if (s >= 3600) String.format(Locale.US, "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60)
    else String.format(Locale.US, "%d:%02d", s / 60, s % 60)
}

/** Seconds with two decimals, e.g. "2.60 s". */
fun secs(v: Double): String = String.format(L, "%.2f s", v)

/** "4× slower" / "2× faster" / "real time" for a speed factor relative to real time. */
fun speedWords(speed: Double): String = when {
    abs(speed - 1) < 1e-6 -> tr("real time")
    speed < 1 -> tr("%s× slower", fmt(1 / speed))
    else -> tr("%s× faster", fmt(speed))
}

/** Seconds with one decimal, e.g. "5.0 s" (Easy mode). */
fun secs1(v: Double): String = String.format(L, "%.1f s", v)

/**
 * Easy mode: a section's rate as speed only – "4× slower", "real time", "2× faster" – relative
 * to real time; the rate that equals the output frame rate shows every recorded frame once and is
 * marked "(original)" (e.g. 9.6× slower at 25 fps for a 240 fps recording).
 */
fun easySpeedLabel(real: Rational, outFps: Rational, r: Rational): String {
    val speed = (r / real).toDouble()
    val words = when {
        abs(speed - 1) < 1e-6 -> tr("real time")
        speed < 1 -> tr("%s× slower", short(1 / speed))
        else -> tr("%s× faster", short(speed))
    }
    return if (r == outFps && r != real) tr("%s (original)", words) else words
}

/**
 * Easy speed choices: whole frame rates only (30, not 29.97 – they would show as the same
 * "8× slower"), plus the original (the output frame rate, e.g. 25 → 9.6× slower) and real
 * time; every label once.
 */
fun easyRates(real: Rational, outFps: Rational): List<Rational> =
    (sectionRates(real) + outFps)
        .filter { Rational.of(it.floor()) == it || it == outFps || it == real }
        .distinct().sorted()
        .distinctBy { easySpeedLabel(real, outFps, it) }

/** Timeline label in Easy: "4× slower" / "real time" / "2× faster", or just "4×" / "1×". */
fun easySpeedShort(real: Rational, r: Rational, long: Boolean): String {
    val speed = (r / real).toDouble()
    return when {
        abs(speed - 1) < 1e-6 -> if (long) tr("real time") else "1×"
        speed < 1 -> if (long) tr("%s× slower", short(1 / speed)) else "${short(1 / speed)}×"
        else -> if (long) tr("%s× faster", short(speed)) else "${short(speed)}×"
    }
}

/** At most one decimal, no trailing ".0" (9.6, 4, 8). */
private fun short(v: Double): String =
    String.format(L, "%.1f", v).removeSuffix("${DOT}0")

/** Desktop frame-rate list (formats.FRAME_RATES), 48 added in 0.93. */
val FPS_CHOICES: List<Rational> =
    listOf("24000/1001", "24", "25", "30000/1001", "30", "48", "50", "60000/1001", "60", "120").map(Rational::parse)

/** Rates offered for a section: 23.976 up to 8× the real rate (desktop limits), plus "original". */
fun sectionRates(real: Rational): List<Rational> {
    val more = listOf("240", "480", "960").map(Rational::parse)
    val max = real * 8
    return (FPS_CHOICES + more + real).filter { it <= max }.distinct().sorted()
}

fun exportFpsLabel(job: LosslessJob, r: Rational): String {
    val j = job.copy(fps = r, segments = emptyList())
    val orig = if (r == job.info.realFps) tr(" (original)") else ""
    return "${fmtFps(r.toDouble())} fps$orig · ${speedWords(j.speed.toDouble())} · ${clock(j.outputDuration.toDouble())}"
}

fun sectionFpsLabel(real: Rational, r: Rational): String {
    val orig = if (r == real) tr(" (original)") else ""
    return "${fmtFps(r.toDouble())} fps$orig · ${speedWords((r / real).toDouble())}"
}
