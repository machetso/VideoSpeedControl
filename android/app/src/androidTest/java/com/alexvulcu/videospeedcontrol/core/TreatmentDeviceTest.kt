package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** .cst files between the phone and the desktop (desktop_smart.cst made by vsc/core/treatment.py). */
@RunWith(AndroidJUnit4::class)
class TreatmentDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext

    private fun fingerprint(f: File) = Treatment.fingerprint(f.length()) {
        ctx.contentResolver.openInputStream(Uri.fromFile(f))!!
    }

    /** A desktop .cst loads onto its clip on the phone (same fingerprint, same frame count). */
    @Test fun desktopTreatmentMatchesItsClip() {
        val clip = TestClips.get("synth_hevc_closed.mp4")
        val d = Treatment.fromJson(TestClips.get("desktop_smart.cst").readText(), "desktop_smart.cst")
        val info = Probe.probe(ctx, Uri.fromFile(clip))
        d.check(info.name, clip.length(), fingerprint(clip), info.frames.count)     // throws if not
        assertEquals(Treatment.Mode.SMART, d.settings.mode)
    }

    /** The phone writes a .cst for the same clip – checked on the laptop with treatment.load. */
    @Test fun writeTreatmentForTheDesktop() {
        val clip = TestClips.get("synth_hevc_closed.mp4")
        val info = Probe.probe(ctx, Uri.fromFile(clip))
        val d = Treatment.Data(info.name, clip.length(), fingerprint(clip), info.frames.count,
            Treatment.Settings(Treatment.Mode.REENCODE, Rational.parse("30000/1001"), null, VideoCodec.AVC,
                Quality.HIGH, 480, sound = true, smartAuto = true, size = 854 to 480),
            Trim(48, 912), listOf(Segment(100, 200, Rational.of(30)), Segment(400, 480, Rational.of(60), true, Rational.of(25))),
            info.uri.toString())
        File(File(ctx.cacheDir, "out").apply { mkdirs() }, "android.cst").writeText(Treatment.toJson(d, info.videoMime))
    }
}
