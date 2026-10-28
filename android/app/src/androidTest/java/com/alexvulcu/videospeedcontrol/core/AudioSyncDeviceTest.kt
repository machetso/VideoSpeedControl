package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream

/**
 * Sound sync at section borders (same test as the desktop's test_section_borders_stay_in_sync):
 * clicks every 0.5 s, three sections. The exports stay in cache/out; the onsets are measured on
 * the laptop with tools/verify/check_clicks.py (it computes the expected times itself).
 */
@RunWith(AndroidJUnit4::class)
class AudioSyncDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext
    private val outDir = File(ctx.cacheDir, "out").apply { mkdirs() }

    private fun export(slower: List<Int>, name: String, reencode: Boolean = false) {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get("synth_clicks240.mp4")))
        val (a, b, c) = slower.map { Rational.of(240L, it.toLong()) }
        val segs = listOf(Segment(100, 340, a), Segment(400, 560, b), Segment(700, 760, c))
        FileOutputStream(File(outDir, name)).use {
            if (reencode) ReencodeExport(ctx, ReencodeJob(info, Rational.of(60), segments = segs), true).run(it.fd)
            else LosslessExport(ctx, LosslessJob(info, Rational.of(240), segments = segs), true).run(it.fd)
        }
    }

    @Test fun moderate() = export(listOf(8, 4, 2), "sync_8_4_2.mp4")

    @Test fun strong() = export(listOf(40, 10, 20), "sync_40_10_20.mp4")

    @Test fun reencoded() = export(listOf(8, 4, 2), "sync_re_8_4_2.mp4", reencode = true)
}
