package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.media.MediaExtractor
import android.media.MediaFormat
import java.nio.ByteBuffer

/**
 * Smart export (desktop: `vsc/core/smart.py`): the clip is copied, only the sections marked for
 * it are re-encoded – with the source codec – and everything is joined into one video track.
 *
 * A copied part must start at a *safe* keyframe: an IDR picture, or (HEVC) a CRA picture not
 * followed by RASL pictures, which reference the GOP before it (open GOP). Re-encoded parts are
 * widened to safe keyframes. This file holds the planning (same rules and rounding as the
 * desktop, so a .cst gives the same parts on both) and the keyframe analysis.
 */
object Smart {
    val DEFAULT_OUT_FPS: Rational = Rational.of(30)

    data class Part(
        val encode: Boolean,       // false = copied
        val start: Int,
        val end: Int,              // exclusive source frame
        val fps: Rational?,        // constant output rate of an encoded part
        val frames: Int,           // output frames
        val duration: Rational,    // seconds
    )

    /** Codecs whose parts can be joined (the desktop's SMART_CODECS). */
    fun supported(videoMime: String) =
        videoMime == MediaFormat.MIMETYPE_VIDEO_HEVC || videoMime == MediaFormat.MIMETYPE_VIDEO_AVC

    // ------------------------------------------------------------------ plan

    /** Source ranges to re-encode (widened to safe keyframes, merged) with their output fps. */
    fun encodeRanges(segments: List<Segment>, trim: Trim, trimEnd: Int, joins: List<Int>): List<Triple<Int, Int, Rational>> {
        val start = trim.start
        val out = mutableListOf<Triple<Int, Int, Rational>>()
        for (s in segments.sortedBy { it.start }) {
            if (!s.reencode || s.end <= start || s.start >= trimEnd) continue
            var a = maxOf(s.start, start)
            var b = minOf(s.end, trimEnd)
            a = joins.filter { it <= a }.maxOrNull() ?: start
            b = joins.filter { it >= b }.minOrNull() ?: trimEnd
            a = maxOf(a, start)
            b = minOf(b, trimEnd)
            val fps = s.outFps ?: DEFAULT_OUT_FPS
            val last = out.lastOrNull()
            if (last != null && a <= last.second) {
                out[out.lastIndex] = Triple(last.first, maxOf(last.second, b), last.third)
            } else {
                out += Triple(a, b, fps)
            }
        }
        return out
    }

    fun plan(job: Timing, joins: List<Int>): List<Part> {
        val start = job.trim.start
        val end = job.trimEnd
        val real = job.info.realFps
        val parts = mutableListOf<Part>()
        var pos = start
        for ((a, b, fps) in encodeRanges(job.segments, job.trim, end, joins) + Triple(end, end, Rational.ONE)) {
            if (a > pos) {
                val ps = Segments.pieces(job.segments, pos, a, real)
                parts += Part(false, pos, a, null, a - pos, Segments.duration(ps))
            }
            if (b > a) {
                val ps = Segments.pieces(job.segments, a, b, real)
                val n = maxOf(1L, (Segments.duration(ps) * fps).roundHalfEven()).toInt()
                parts += Part(true, a, b, fps, n, Rational.of(n.toLong()) / fps)
            }
            pos = maxOf(pos, b)
        }
        return parts
    }

    // ------------------------------------------------------------------ safe join points

    /**
     * VCL NAL unit types of one sample. MediaExtractor hands out H.264 / HEVC samples of MP4
     * files in Annex-B form (start codes 00 00 01 / 00 00 00 01); stored MP4 samples are
     * length-prefixed ([lengthSize] bytes). Both are read; null if neither layout fits.
     */
    fun nalTypes(sample: ByteBuffer, size: Int, hevc: Boolean, lengthSize: Int = 4): List<Int>? {
        fun vcl(h: Int): Int? {
            val t = if (hevc) (h shr 1) and 0x3f else h and 0x1f
            return t.takeIf { (hevc && it < 32) || (!hevc && (it == 1 || it == 5)) }
        }
        fun b(i: Int) = sample.get(i).toInt() and 0xff
        if (size >= 4 && b(0) == 0 && b(1) == 0 && (b(2) == 1 || (b(2) == 0 && b(3) == 1))) {
            val types = mutableListOf<Int>()
            var i = 0
            while (i + 3 < size) {
                if (b(i) == 0 && b(i + 1) == 0 && b(i + 2) == 1) {
                    vcl(b(i + 3))?.let { types += it }
                    i += 3
                } else i++
            }
            return types
        }
        val types = mutableListOf<Int>()
        var p = 0
        while (p < size) {
            if (p + lengthSize + 1 > size) return null
            var n = 0L
            for (i in 0 until lengthSize) n = (n shl 8) or (b(p + i).toLong())
            if (n == 0L || p + lengthSize + n > size) return null
            vcl(b(p + lengthSize))?.let { types += it }
            p += lengthSize + n.toInt()
        }
        return types
    }

    /** IDR, or (HEVC) a CRA not followed by RASL pictures; H.264: IDR. */
    fun safe(types: List<Int>, nextTypes: List<Int>?, hevc: Boolean): Boolean {
        if (!hevc) return 5 in types
        if (types.any { it == 19 || it == 20 }) return true
        return 21 in types && nextTypes?.any { it == 8 || it == 9 } != true
    }

    /**
     * Display indices of keyframes where a copied part may start. Reads only the keyframe samples
     * and the sample after each (MediaExtractor gives the codec's samples as stored: MP4 =
     * length-prefixed NAL units). Throws if the clip cannot be read.
     */
    fun joinPoints(context: Context, info: ClipInfo): List<Int> {
        if (!supported(info.videoMime)) return emptyList()
        val hevc = info.videoMime == MediaFormat.MIMETYPE_VIDEO_HEVC
        val ex = MediaExtractor()
        try {
            ex.setDataSource(context, info.uri, null)
            val track = (0 until ex.trackCount).first {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            }
            ex.selectTrack(track)
            val buf = ByteBuffer.allocateDirect(maxOf(info.width * info.height * 2, 4 shl 20))
            val out = mutableListOf<Int>()
            for (k in info.frames.keyframes) {
                ex.seekTo(info.frames.ptsUs[k], MediaExtractor.SEEK_TO_CLOSEST_SYNC)
                if (ex.sampleTime != info.frames.ptsUs[k]) continue
                val size = ex.readSampleData(buf, 0)
                val types = nalTypes(buf, size, hevc) ?: error("Unexpected sample layout at frame $k")
                ex.advance()
                val nextSize = ex.readSampleData(buf, 0)
                val next = if (nextSize > 0) nalTypes(buf, nextSize, hevc) else null
                if (safe(types, next, hevc)) out += k
            }
            return out
        } finally {
            ex.release()
        }
    }
}
