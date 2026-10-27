package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

/** Proxy build speed and completeness (timing goes to logcat, tag VscProxy). */
@RunWith(AndroidJUnit4::class)
class ProxyDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext

    private fun build(name: String): Proxy {
        val info = Probe.probe(ctx, Uri.fromFile(TestClips.get(name)))
        val t0 = System.nanoTime()
        val p = runBlocking { Proxy.build(ctx, info) {} }
        val s = (System.nanoTime() - t0) / 1e9
        Log.i("VscProxy", "$name: ${p.count} frames in ${"%.2f".format(s)} s = " +
            "${"%.0f".format(p.count / s)} fps, ${p.bytes / 1024} KiB, ${p.width}x${p.height}")
        assertEquals(info.frames.count, p.ready)
        for (f in listOf(0, p.count / 2, p.count - 1)) assertNotNull(p.bitmap(f))
        return p
    }

    /** Save proxy frames to cache/out for a visual check (synthetic clips only). */
    private fun save(p: Proxy, name: String, frames: List<Int>) {
        val dir = java.io.File(ctx.cacheDir, "out").apply { mkdirs() }
        for (f in frames) {
            java.io.File(dir, "proxy_${name}_$f.jpg").outputStream().use {
                p.bitmap(f)!!.compress(android.graphics.Bitmap.CompressFormat.JPEG, 90, it)
            }
        }
    }

    @Test fun pixel120() { build("PXL_20261025_152730266.mp4") }

    @Test fun synthHevc240() { save(build("synth_hevc240.mp4"), "hevc240", listOf(0, 539)) }

    @Test fun synthRotated() {
        val p = build("synth_avc120_rot.mp4")
        assertEquals(270, p.width)          // 1280×720 rotated 90° → portrait
        save(p, "rot", listOf(0))
    }
}
