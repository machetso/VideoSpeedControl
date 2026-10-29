package com.alexvulcu.videospeedcontrol.ui

import com.alexvulcu.videospeedcontrol.core.LosslessJob
import com.alexvulcu.videospeedcontrol.core.Rational
import java.util.Locale
import kotlin.math.abs
import kotlin.math.round

fun fmt(v: Double): String = String.format(Locale.US, "%.3g", v).let {
    if ('e' in it) String.format(Locale.US, "%.0f", v) else it
}

fun fmtFps(v: Double): String = String.format(Locale.US, "%.3f", v).trimEnd('0').trimEnd('.')

fun clock(seconds: Double): String {
    val s = round(seconds).toLong()
    return if (s >= 3600) String.format(Locale.US, "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60)
    else String.format(Locale.US, "%d:%02d", s / 60, s % 60)
}

/** Seconds with two decimals, e.g. "2.60 s". */
fun secs(v: Double): String = String.format(Locale.US, "%.2f s", v)

/** "4× slower" / "2× faster" / "real time" for a speed factor relative to real time. */
fun speedWords(speed: Double): String = when {
    abs(speed - 1) < 1e-6 -> "real time"
    speed < 1 -> "${fmt(1 / speed)}× slower"
    else -> "${fmt(speed)}× faster"
}

/** Seconds with one decimal, e.g. "5.0 s" (Easy mode). */
fun secs1(v: Double): String = String.format(Locale.US, "%.1f s", v)

/**
 * Easy mode: a section's rate as speed only – "4× slower", "real time", "2× faster" – relative
 * to real time; the rate that equals the output frame rate shows every recorded frame once and is
 * marked "(original)" (e.g. 9.6× slower at 25 fps for a 240 fps recording).
 */
fun easySpeedLabel(real: Rational, outFps: Rational, r: Rational): String {
    val speed = (r / real).toDouble()
    val words = when {
        abs(speed - 1) < 1e-6 -> "real time"
        speed < 1 -> "${short(1 / speed)}× slower"
        else -> "${short(speed)}× faster"
    }
    return if (r == outFps && r != real) "$words (original)" else words
}

/** At most one decimal, no trailing ".0" (9.6, 4, 8). */
private fun short(v: Double): String =
    String.format(Locale.US, "%.1f", v).removeSuffix(".0")

/** Desktop frame-rate list (formats.FPS). */
val FPS_CHOICES: List<Rational> =
    listOf("24000/1001", "24", "25", "30000/1001", "30", "50", "60000/1001", "60", "120").map(Rational::parse)

/** Rates offered for a section: 23.976 up to 8× the real rate (desktop limits), plus "original". */
fun sectionRates(real: Rational): List<Rational> {
    val more = listOf("240", "480", "960").map(Rational::parse)
    val max = real * 8
    return (FPS_CHOICES + more + real).filter { it <= max }.distinct().sorted()
}

fun exportFpsLabel(job: LosslessJob, r: Rational): String {
    val j = job.copy(fps = r, segments = emptyList())
    val orig = if (r == job.info.realFps) " (original)" else ""
    return "${fmtFps(r.toDouble())} fps$orig · ${speedWords(j.speed.toDouble())} · ${clock(j.outputDuration.toDouble())}"
}

fun sectionFpsLabel(real: Rational, r: Rational): String {
    val orig = if (r == real) " (original)" else ""
    return "${fmtFps(r.toDouble())} fps$orig · ${speedWords((r / real).toDouble())}"
}
