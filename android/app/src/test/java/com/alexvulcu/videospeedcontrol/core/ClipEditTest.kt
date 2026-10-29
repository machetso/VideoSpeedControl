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

    @Test fun quickEndFollowsTheSectionBefore() {
        val e = clip()
        assertEquals(0, e.quickStart(300))                              // nothing yet: from the start
        val a = e.addSection(e.quickStart(299), 299, r("25"))
        assertEquals(listOf(Segment(0, 300, r("25"))), a.segments)
        assertEquals(300, a.quickStart(500))                           // right after the section before
        val b = a.addSection(a.quickStart(499), 499, r("60"))
        assertEquals(listOf(Segment(0, 300, r("25")), Segment(300, 500, r("60"))), b.segments)
        assertEquals(300, b.quickStart(400))                           // inside a section: split it
        assertEquals(10, e.withIn(10, snap = false).quickStart(100))   // from the trim start
    }

    @Test fun draggingABorderMovesBothNeighbours() {
        val e = clip().addSection(0, 299, r("25")).addSection(300, 499, r("60"))
        assertEquals(listOf(300, 500), e.borders())
        assertEquals(1 to 499, e.borderRange(300))
        assertEquals(listOf(Segment(0, 350, r("25")), Segment(350, 500, r("60"))), e.movedBorder(300, 350))
        assertEquals(499, e.movedBorder(300, 900)[0].end)              // stops before the next border
        // a border to real time: the gap grows / shrinks
        assertEquals(301 to 960, e.borderRange(500))         // the section keeps at least one frame
        assertEquals(Segment(300, 700, r("60")), e.movedBorder(500, 700)[1])
    }

    @Test fun smoothFlagsSitOnBothSidesOfABorder() {
        val e = clip().addSection(0, 299, r("25")).addSection(300, 499, r("60"))
        val s = e.setSmooth(1, atStart = true, on = true)
        assertTrue(s.segments[0].smoothEnd && s.segments[1].smoothStart)
        assertEquals(r("25"), s.neighbourRate(1, atStart = true))
        assertEquals(r("240"), s.neighbourRate(1, atStart = false))      // real time after it
        assertEquals(null, s.neighbourRate(0, atStart = true))           // clip start
        assertEquals(e.segments, s.undo().segments)
    }

    @Test fun editingASectionRange() {
        val e = clip().addSection(100, 199, r("25")).addSection(300, 399, r("60"))
        val m = e.setSectionRange(0, 150, 349)                          // overlaps the next: cut back
        assertEquals(listOf(Segment(150, 350, r("25")), Segment(350, 400, r("60"))), m.segments)
    }
}
