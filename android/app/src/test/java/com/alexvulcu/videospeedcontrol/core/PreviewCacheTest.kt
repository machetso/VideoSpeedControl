package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito
import java.io.File
import java.nio.file.Files

/** Stored previews: chunks with CRC, partial rebuild, clean-up rules. */
class PreviewCacheTest {
    private val tmp: File = Files.createTempDirectory("vsc-previews").toFile()
    private val cache = PreviewCache(Mockito.mock(Context::class.java).also { Mockito.`when`(it.filesDir).thenReturn(tmp) })
    private val fp = "ab".repeat(32)

    private fun proxy() = Proxy(100, 48, 27, intArrayOf(0, 30, 60, 90))
    private fun jpeg(f: Int) = ByteArray(50 + f) { (it + f).toByte() }

    /** A proxy whose chunks are written as they complete (like the build does). */
    private fun filled(): Proxy {
        val p = proxy()
        p.onChunkComplete = { i -> cache.writeChunk(fp, p, i) }
        for (f in 0 until 100) p.put(f, jpeg(f))
        return p
    }

    @Test fun chunksFollowTheKeyframes() {
        assertEquals(listOf(0..29, 30..59, 60..89, 90..99), proxy().chunks)
    }

    @Test fun storedChunksLoadAgain() {
        filled()
        val q = proxy()
        assertEquals(setOf(0, 1, 2, 3), cache.loadChunks(fp, q))
        for (f in 0 until 100) assertTrue(q.jpeg(f)!!.contentEquals(jpeg(f)))
    }

    @Test fun aDamagedChunkIsRebuiltAlone() {
        filled()
        val f = File(cache.dir(fp), "chunk_30.bin")
        val b = f.readBytes(); b[b.size / 2] = (b[b.size / 2] + 1).toByte(); f.writeBytes(b)   // one flipped byte
        File(cache.dir(fp), "chunk_90.bin").delete()                                           // one missing
        val q = proxy()
        assertEquals(setOf(0, 2), cache.loadChunks(fp, q))
        assertFalse(q.has(30)); assertFalse(q.has(95))
    }

    @Test fun otherSettingsAreNotLoaded() {
        filled()
        val other = Proxy(100, 64, 36, intArrayOf(0, 30, 60, 90))       // another size
        assertEquals(emptySet<Int>(), cache.loadChunks(fp, other))
    }

    @Test fun cleanupKeepsOpenBatchAndCst() {
        for (name in listOf("open", "batch", "cst", "old")) {
            File(cache.dir(name).apply { mkdirs() }, "chunk_0.bin").writeBytes(ByteArray(1000))
        }
        assertEquals(1, cache.cleanup("open", setOf("batch"), setOf("cst")))
        assertEquals(setOf("open", "batch", "cst"), cache.root.list()!!.toSet())
        // over the cap: the least recently used without a .cst goes first, the open one never
        cache.dir("batch").setLastModified(1_000)
        cache.dir("cst").setLastModified(500)
        assertEquals(1, cache.cleanup("open", setOf("batch"), setOf("cst"), capBytes = 2500))
        assertEquals(setOf("open", "cst"), cache.root.list()!!.toSet())
    }

    @Test fun joinsAndThumbs() {
        cache.writeJoins(fp, 100, "a.mp4", listOf(0, 30, 60))
        assertEquals(listOf(0, 30, 60), cache.loadJoins(fp, 100))
        assertEquals(null, cache.loadJoins(fp, 99))                      // another frame count
        cache.writeThumbs(fp, listOf(0 to jpeg(0), 30 to jpeg(30)))
        assertEquals(listOf(0, 30), cache.loadThumbs(fp)!!.map { it.first })
    }
}
