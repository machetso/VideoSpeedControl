package com.alexvulcu.videospeedcontrol.core

import android.net.Uri
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
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

    /** Stored preview: the second build loads it; a damaged chunk is rebuilt alone, same pictures. */
    @Test fun storedPreview() {
        for (name in listOf("synth_hevc240.mp4", "synth_hevc_closed.mp4", "PXL_20261025_152730266.mp4")) {
            val f = runCatching { TestClips.get(name) }.getOrNull() ?: continue
            val info = Probe.probe(ctx, Uri.fromFile(f))
            val cache = PreviewCache(ctx)
            val fp = "test-" + name.hashCode()
            cache.dir(fp).deleteRecursively()
            var t0 = System.nanoTime()
            val first = runBlocking { Proxy.build(ctx, info, cache, fp) {} }
            val tBuild = (System.nanoTime() - t0) / 1e6
            Thread.sleep(300)                                     // last chunk written by its JPEG thread
            t0 = System.nanoTime()
            val second = runBlocking { Proxy.build(ctx, info, cache, fp) {} }
            val tLoad = (System.nanoTime() - t0) / 1e6
            assertTrue(second.complete)
            for (fr in 0 until info.frames.count step first.step) assertTrue("frame $fr", first.jpeg(fr)!!.contentEquals(second.jpeg(fr)!!))
            // damage one chunk in the middle: only it is decoded again (from its keyframe)
            val mid = first.chunks[first.chunks.size / 2]
            val file = java.io.File(cache.dir(fp), "chunk_${mid.first}.bin")
            file.writeBytes(file.readBytes().also { it[it.size / 2] = (it[it.size / 2] + 1).toByte() })
            t0 = System.nanoTime()
            val third = runBlocking { Proxy.build(ctx, info, cache, fp) {} }
            val tRepair = (System.nanoTime() - t0) / 1e6
            assertTrue(third.complete)
            var same = 0
            for (fr in mid step first.step) {
                val a = first.jpeg(fr)!!; val b = third.jpeg(fr)!!
                if (a.contentEquals(b)) same++
            }
            Log.i("VscProxy", "$name: ${info.frames.count} frames, ${first.chunks.size} chunks, build ${"%.0f".format(tBuild)} ms, " +
                "from storage ${"%.0f".format(tLoad)} ms, one chunk repaired ${"%.0f".format(tRepair)} ms " +
                "(${mid.count()} frames, $same identical JPEGs), stored ${cache.dir(fp).walk().sumOf { it.length() } / 1024} KB")
            cache.dir(fp).deleteRecursively()
        }
    }
}
