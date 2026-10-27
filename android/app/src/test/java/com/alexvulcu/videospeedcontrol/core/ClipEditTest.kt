package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito

class ClipEditTest {
    private val r = Rational::parse

    /** 240 fps clip, 960 frames, keyframe every 48 frames. */
    private fun clip(): ClipEdit {
        val fm = FrameMap(LongArray(960) { Math.round(it * 1e6 / 240) }, IntArray(20) { it * 48 })
        val info = ClipInfo(
            uri = Mockito.mock(Uri::class.java), name = "c.mp4", sizeBytes = 1, videoMime = "video/hevc",
            width = 1920, height = 1080, rotation = 0, durationUs = 4_000_000, fps = r("240"),
            captureFps = null, bitrate = null, hdr = null, audio = null, audioRate = null,
            recorded = null, frames = fm,
        )
        return ClipEdit(info)
    }

    @Test fun addSectionAnyOrderIncludesBothEnds() {
        val e = clip().addSection(200, 100, r("30"))
        assertEquals(listOf(Segment(100, 201, r("30"))), e.segments)
        assertEquals(0, e.sectionAt(100))
        assertEquals(-1, e.sectionAt(201))
    }

    @Test fun undoRedo() {
        val e = clip().addSection(100, 199, r("30")).addSection(150, 299, r("60"))
        assertEquals(listOf(Segment(100, 150, r("30")), Segment(150, 300, r("60"))), e.segments)
        val u = e.undo()
        assertEquals(listOf(Segment(100, 200, r("30"))), u.segments)
        assertEquals("Add section 151–300 at 60 fps", u.redo.last().what)
        assertEquals(e.segments, u.redo().segments)
        assertEquals(emptyList<Segment>(), u.undo().segments)
        // a new edit clears redo
        assertTrue(u.removeSection(0).redo.isEmpty())
    }

    @Test fun undoIsCapped() {
        var e = clip()
        repeat(250) { e = e.addSection(it, it, r("30")) }
        assertEquals(ClipEdit.MAX_UNDO, e.undo.size)
    }

    @Test fun trimSnapsToKeyframes() {
        val e = clip().withIn(70)                 // keyframes 48, 96 → 48 is nearer
        assertEquals(Trim(48, null), e.trim)
        val e2 = e.withOut(150)                   // end 151 → GOP boundary 144
        assertEquals(Trim(48, 144), e2.trim)
        assertEquals(Trim(48, null), e2.withOut(959).trim)
        // in-point after the out-point drops the out-point
        assertEquals(Trim(192, null), e2.withIn(200).trim)
    }

    @Test fun magneticCursor() {
        val e = clip().addSection(100, 199, r("30")).addSection(400, 499, r("60"))
        // nothing marked: snap to the frame after a section (200, 500)
        assertEquals(200, e.snap(195, 8, null))
        assertEquals(500, e.snap(507, 8, null))
        assertEquals(300, e.snap(300, 8, null))          // too far from any border
        // marking an end: snap to the frame before the next section (399)
        assertEquals(399, e.snap(392, 8, pendingStart = 250))
        assertEquals(192, e.snap(192, 8, pendingStart = 250))   // section before the start: ignored
    }

    @Test fun setFpsAndClear() {
        val e = clip().addSection(0, 47, r("30")).setSectionFps(0, r("60"))
        assertEquals(r("60"), e.segments[0].fps)
        val c = e.clearSections()
        assertTrue(c.segments.isEmpty())
        assertEquals(e.segments, c.undo().segments)
    }
}
