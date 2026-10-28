package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.net.Uri
import java.io.FileDescriptor

/**
 * One export as a self-contained description: the clip and a treatment snapshot (what a .cst
 * holds). Single exports and batch entries are both tasks; the export service runs them one
 * after another and they survive an app restart (only uri + JSON are stored).
 */
data class ExportTask(
    val id: Long,
    val uri: Uri,
    val treatment: Treatment.Data,
    val sourceMime: String,
) {
    val label: String get() = describe(treatment)

    companion object {
        /** Short description like the desktop's batch.describe ("Smart, 3 sections (1 re-encoded)"). */
        fun describe(t: Treatment.Data): String {
            val s = t.settings
            val inTrim = t.segments.filter { it.start < (t.trim.end ?: Int.MAX_VALUE) && it.end > t.trim.start }
            val fps = "${LosslessJob.pyG(s.fps.toDouble(), 5)} fps"
            return when (s.mode) {
                Treatment.Mode.LOSSLESS -> if (inTrim.isEmpty()) "Lossless @ $fps"
                    else "Lossless, ${inTrim.size} section${if (inTrim.size != 1) "s" else ""}"
                Treatment.Mode.SMART -> {
                    val enc = inTrim.count { it.reencode }
                    "Smart @ $fps ($enc of ${inTrim.size} parts re-encoded)"
                }
                Treatment.Mode.REENCODE -> "Re-encode ${s.codec.label.substringBefore(" (")} @ $fps" +
                    if (inTrim.isNotEmpty()) ", ${inTrim.size} section${if (inTrim.size != 1) "s" else ""}" else ""
            }
        }
    }
}

/** Builds the job for a task and runs it into an output file. */
object Exporter {
    class Running(val cancel: () -> Unit, val run: (FileDescriptor, (Float) -> Unit) -> Int,
                  val stem: String, val extension: String, val mime: String)

    /** Probe the clip, check it is still the treatment's video, set up the matching export. */
    fun prepare(context: Context, task: ExportTask): Running {
        val t = task.treatment
        val info = try {
            Probe.probe(context, task.uri)
        } catch (e: Exception) {
            // clips opened via "Share" / "Open with" are only readable until the app is closed
            throw Treatment.TreatmentError("VideoSpeedControl can no longer read ${t.sourceName}. If it was opened " +
                "through another app (Share / Open with), open it again with “Choose clip” and add it to the batch again.")
        }
        if (info.sizeBytes >= 0 && info.sizeBytes != t.sourceSize) {
            throw Treatment.TreatmentError("${info.name} has changed since it was added (${info.sizeBytes} bytes, " +
                "was ${t.sourceSize}).")
        }
        val s = t.settings
        val sound = s.sound
        return when (s.mode) {
            Treatment.Mode.LOSSLESS -> {
                val job = LosslessJob(info, s.fps, t.trim, t.segments)
                val blockers = job.blockers()
                if (blockers.isNotEmpty()) throw IllegalStateException(blockers.joinToString("; "))
                val c = Muxing.containerFor(info.videoMime)!!
                val x = LosslessExport(context, job, sound)
                Running({ x.cancelled = true }, { fd, p -> x.run(fd, p) }, job.fileStem(), c.extension, c.mime)
            }
            Treatment.Mode.SMART -> {
                val job = SmartJob(info, s.fps, t.trim, t.segments, Smart.joinPoints(context, info), s.quality)
                val blockers = job.blockers()
                if (blockers.isNotEmpty()) throw IllegalStateException(blockers.joinToString("; "))
                val x = SmartExport(context, job, sound)
                Running({ x.cancelled = true }, { fd, p -> x.run(fd, p) }, job.fileStem(), "mp4", "video/mp4")
            }
            Treatment.Mode.REENCODE -> {
                val job = ReencodeJob(info, s.fps, s.speed, t.trim, t.segments, s.codec, s.shortSide, s.quality)
                val blockers = job.blockers()
                if (blockers.isNotEmpty()) throw IllegalStateException(blockers.joinToString("; "))
                val x = ReencodeExport(context, job, sound)
                Running({ x.cancelled = true }, { fd, p -> x.run(fd, p) }, job.fileStem(), "mp4", "video/mp4")
            }
        }
    }
}
