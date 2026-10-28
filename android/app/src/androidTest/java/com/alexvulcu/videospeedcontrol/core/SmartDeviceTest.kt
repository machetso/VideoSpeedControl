package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Safe join points on the phone = what the desktop's smart.join_points finds for the same clips. */
@RunWith(AndroidJUnit4::class)
class SmartDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext

    private fun joins(name: String): Pair<ClipInfo, List<Int>> {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get(name)))
        return info to Smart.joinPoints(ctx, info)
    }

    @Test fun hevcOpenGopOnlyIdr() = assertEquals(listOf(0), joins("synth_hevc240.mp4").second)

    @Test fun h264ClosedGopAllKeyframes() {
        val (info, j) = joins("synth_avc120_rot.mp4")
        assertEquals(listOf(0, 60, 120, 180, 240, 300), j)
        assertEquals(info.frames.keyframes.toList(), j)
    }

    /** Pixel HEVC slow-mo: closed GOPs (IDR every 30 frames, see NalSurveyTest) → all keyframes. */
    @Test fun pixelAllKeyframes() {
        val (info, j) = joins("PXL_20261025_152730266.mp4")
        Log.i("VscSmart", "Pixel: ${j.size} of ${info.frames.keyframes.size} keyframes are safe joins")
        assertTrue(j.isNotEmpty())
        assertEquals(info.frames.keyframes.toList(), j)
    }
}
