package com.alexvulcu.videospeedcontrol.core

/**
 * Edit state of one clip: trim and speed sections, with undo / redo of section edits
 * (desktop: `Clip.edit_segments`, 200 steps). Immutable values in, new values out – the UI keeps
 * the current [ClipEdit] in its state.
 */
data class ClipEdit(
    val info: ClipInfo,
    val trim: Trim = Trim(),
    val segments: List<Segment> = emptyList(),
    val undo: List<Step> = emptyList(),
    val redo: List<Step> = emptyList(),
) {
    /** One undoable change: the sections before it and what it was ("Add section 120–240"). */
    data class Step(val segments: List<Segment>, val what: String)

    private val frames get() = info.frames

    fun job(fps: Rational) = LosslessJob(info, fps, trim, segments)

    // ------------------------------------------------------------------ sections

    /** Change the sections; the old ones go onto the undo stack. */
    fun editSegments(new: List<Segment>, what: String): ClipEdit {
        if (new == segments) return this
        return copy(segments = new, undo = (undo + Step(segments, what)).takeLast(MAX_UNDO), redo = emptyList())
    }

    fun undo(): ClipEdit {
        val step = undo.lastOrNull() ?: return this
        return copy(segments = step.segments, undo = undo.dropLast(1), redo = redo + Step(segments, step.what))
    }

    fun redo(): ClipEdit {
        val step = redo.lastOrNull() ?: return this
        return copy(segments = step.segments, redo = redo.dropLast(1), undo = undo + Step(segments, step.what))
    }

    /** Section from [first] to [last] (both included, any order) at [fps]. */
    fun addSection(first: Int, last: Int, fps: Rational): ClipEdit {
        val a = minOf(first, last).coerceIn(0, frames.count - 1)
        val b = maxOf(first, last).coerceIn(0, frames.count - 1) + 1
        return editSegments(Segments.add(segments, Segment(a, b, fps)),
            "Add section ${a + 1}–$b at ${fpsLabel(fps)} fps")
    }

    fun setSectionFps(index: Int, fps: Rational): ClipEdit {
        val s = segments.getOrNull(index) ?: return this
        return editSegments(segments.toMutableList().also { it[index] = s.copy(fps = fps) },
            "Section ${s.start + 1}–${s.end}: ${fpsLabel(fps)} fps")
    }

    fun removeSection(index: Int): ClipEdit {
        val s = segments.getOrNull(index) ?: return this
        return editSegments(segments.filterIndexed { i, _ -> i != index }, "Remove section ${s.start + 1}–${s.end}")
    }

    fun clearSections(): ClipEdit = editSegments(emptyList(), "Clear sections")

    /**
     * Magnetic cursor (desktop `Timeline._snap`): before a section start is marked, [frame]
     * snaps to the frame right after a section (so a new section can follow it seamlessly);
     * while marking an end ([pendingStart] set), to the frame right before the next section.
     * Only within [radius] frames; otherwise [frame] is returned unchanged.
     */
    fun snap(frame: Int, radius: Int, pendingStart: Int?): Int {
        val candidates = if (pendingStart == null) segments.map { it.end }
        else segments.filter { it.start > pendingStart }.map { it.start - 1 }
        val best = candidates.filter { it in 0 until frames.count }.minByOrNull { kotlin.math.abs(it - frame) }
            ?: return frame
        return if (kotlin.math.abs(best - frame) <= radius) best else frame
    }

    /** Index of the section containing [frame], or -1. */
    fun sectionAt(frame: Int) = segments.indexOfFirst { frame >= it.start && frame < it.end }

    // ------------------------------------------------------------------ trim (lossless: keyframes)

    /**
     * New in-point (first frame); drops an out-point before it. [snap] (lossless) moves it to
     * the nearest keyframe – re-encoding cuts at any frame.
     */
    fun withIn(frame: Int, snap: Boolean = true): ClipEdit {
        val c = frame.coerceIn(0, frames.count - 1)
        val f = if (snap) frames.snapIn(c) else c
        val end = trim.end
        return copy(trim = Trim(f, if (end != null && end <= f) null else end))
    }

    /** New out-point; [last] is the last frame to include ([snap]: nearest GOP boundary). */
    fun withOut(last: Int, snap: Boolean = true): ClipEdit {
        val total = frames.count
        val e = maxOf(1, minOf(last + 1, total))
        val end = if (snap) frames.snapOut(e) else e
        val start = if (end > trim.start) trim.start else 0
        return copy(trim = Trim(start, if (end >= total) null else end))
    }

    fun clearTrim(): ClipEdit = copy(trim = Trim())

    /** The current trim moved to keyframes / GOP boundaries (desktop `snapped_trim`). */
    fun snappedTrim(): ClipEdit {
        val start = frames.snapIn(trim.start)
        var end = trim.end?.let { frames.snapOut(it) }
        if (end != null && end <= start) end = frames.keyframeAfter(start)
        return copy(trim = Trim(start, if (end == null || end >= frames.count) null else end))
    }

    fun reencodeJob(fps: Rational, speed: Rational?, codec: VideoCodec, shortSide: Int?, quality: Quality) =
        ReencodeJob(info, fps, speed, trim, segments, codec, shortSide, quality)

    val trimEnd: Int get() = trim.end ?: frames.count

    companion object {
        const val MAX_UNDO = 200

        fun fpsLabel(fps: Rational): String =
            String.format(java.util.Locale.US, "%.3f", fps.toDouble()).trimEnd('0').trimEnd('.')
    }
}
