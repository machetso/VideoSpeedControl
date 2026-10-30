package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.File
import java.util.zip.CRC32

/**
 * Stored previews (user, 0.93): the scrubbing proxy of a video, its smart keyframe analysis and
 * its timeline thumbnails, so a video opened again does not rebuild them. One folder per video
 * in the app's private storage, named by the .cst fingerprint (a renamed / moved file still
 * matches, a changed file does not). The proxy is kept in chunks from keyframe to keyframe, each
 * with a CRC: a broken or missing chunk is rebuilt alone, and chunks are written while the proxy
 * is built, so an interrupted build continues where it stopped.
 */
class PreviewCache(context: Context) {
    val root = File(context.filesDir, "previews")

    fun dir(fingerprint: String) = File(root, fingerprint)

    // ------------------------------------------------------------------ proxy chunks

    /** Reads every valid chunk of [proxy]'s video into it; returns the chunk indices loaded. */
    fun loadChunks(fingerprint: String, proxy: Proxy): Set<Int> {
        val d = dir(fingerprint)
        if (!d.isDirectory) return emptySet()
        val loaded = HashSet<Int>()
        for ((i, range) in proxy.chunks.withIndex()) {
            val f = File(d, "chunk_${range.first}.bin")
            if (!f.isFile) continue
            val entries = readBlock(f, header = proxyHeader(proxy, range)) ?: continue
            val wanted = range.filter { it % proxy.step == 0 }
            if (entries.map { it.first } != wanted) continue
            for ((frame, jpeg) in entries) proxy.put(frame, jpeg)
            loaded += i
        }
        if (loaded.isNotEmpty()) touch(fingerprint)
        return loaded
    }

    /** Writes chunk [index] of [proxy] (all its pictures must be there). */
    fun writeChunk(fingerprint: String, proxy: Proxy, index: Int) {
        val range = proxy.chunks[index]
        val entries = range.filter { it % proxy.step == 0 }.map { it to (proxy.jpeg(it) ?: return) }
        writeBlock(File(dir(fingerprint).apply { mkdirs() }, "chunk_${range.first}.bin"),
            proxyHeader(proxy, range), entries)
    }

    private fun proxyHeader(p: Proxy, range: IntRange) =
        intArrayOf(VERSION, p.count, p.width, p.height, p.step, range.first, range.last + 1, Proxy.QUALITY)

    // ------------------------------------------------------------------ thumbnails, keyframe analysis

    fun loadThumbs(fingerprint: String): List<Pair<Int, ByteArray>>? =
        File(dir(fingerprint), "thumbs.bin").takeIf { it.isFile }?.let { readBlock(it, intArrayOf(VERSION)) }

    fun writeThumbs(fingerprint: String, thumbs: List<Pair<Int, ByteArray>>) =
        writeBlock(File(dir(fingerprint).apply { mkdirs() }, "thumbs.bin"), intArrayOf(VERSION), thumbs)

    /** Safe join keyframes of the smart export (null = not stored). */
    fun loadJoins(fingerprint: String, frames: Int): List<Int>? = runCatching {
        val o = JSONObject(File(dir(fingerprint), "meta.json").readText())
        if (o.getInt("version") != VERSION || o.getInt("frames") != frames || !o.has("joins")) return null
        val a = o.getJSONArray("joins")
        (0 until a.length()).map { a.getInt(it) }
    }.getOrNull()

    fun writeJoins(fingerprint: String, frames: Int, name: String, joins: List<Int>) {
        val f = File(dir(fingerprint).apply { mkdirs() }, "meta.json")
        val o = JSONObject().put("version", VERSION).put("frames", frames).put("name", name)
            .put("joins", JSONArray(joins))
        atomicWrite(f, o.toString().toByteArray())
    }

    /** Marks the preview as used now (the 2 GB cap removes the least recently used first). */
    fun touch(fingerprint: String) {
        dir(fingerprint).takeIf { it.isDirectory }?.setLastModified(System.currentTimeMillis())
    }

    // ------------------------------------------------------------------ clean-up

    /**
     * Rule (user, 0.93): a preview stays while its video is open, in the batch list ([inUse]) or
     * has a .cst in the treatments folder ([withCst]); every other one is deleted. Above [capBytes]
     * the least recently used go first – previews without a .cst before those with one; the open
     * video ([open]) is never removed. Returns the number of previews deleted.
     */
    fun cleanup(open: String?, inUse: Set<String>, withCst: Set<String>, capBytes: Long = CAP_BYTES): Int {
        val dirs = root.listFiles { f -> f.isDirectory }?.toList() ?: return 0
        var deleted = 0
        val kept = mutableListOf<File>()
        for (d in dirs) {
            val fp = d.name
            if (fp == open || fp in inUse || fp in withCst) kept += d
            else if (d.deleteRecursively()) deleted++
        }
        var total = kept.sumOf { size(it) }
        val order = kept.filter { it.name != open }
            .sortedWith(compareBy<File>({ it.name in withCst }, { it.lastModified() }))
        for (d in order) {
            if (total <= capBytes) break
            total -= size(d)
            if (d.deleteRecursively()) deleted++
        }
        return deleted
    }

    /** Deletes every stored preview (menu "Delete previews"); returns how many. */
    fun clearAll(): Int = root.listFiles { f -> f.isDirectory }?.count { it.deleteRecursively() } ?: 0

    fun totalBytes(): Long = root.listFiles()?.sumOf { size(it) } ?: 0L

    private fun size(f: File): Long = if (f.isDirectory) f.listFiles()?.sumOf { size(it) } ?: 0L else f.length()

    // ------------------------------------------------------------------ file format

    /**
     * Block file: "VSCP", header ints, entry count, entries (frame, length, bytes), CRC32 of all
     * of that. Written to a temporary file and renamed, so a crash leaves the old or no file.
     */
    private fun writeBlock(f: File, header: IntArray, entries: List<Pair<Int, ByteArray>>) {
        val buf = ByteArrayOutputStream(entries.sumOf { it.second.size } + 64)
        DataOutputStream(buf).use { out ->
            out.write(MAGIC)
            out.writeInt(header.size)
            header.forEach(out::writeInt)
            out.writeInt(entries.size)
            for ((frame, data) in entries) {
                out.writeInt(frame); out.writeInt(data.size); out.write(data)
            }
        }
        val crc = CRC32().apply { update(buf.toByteArray()) }.value
        DataOutputStream(buf).use { it.writeLong(crc) }
        atomicWrite(f, buf.toByteArray())
    }

    /** Entries of a block file, or null if it is damaged or was written for other settings. */
    private fun readBlock(f: File, header: IntArray): List<Pair<Int, ByteArray>>? = runCatching {
        val bytes = f.readBytes()
        if (bytes.size < 16) return null
        val body = bytes.size - 8
        val crc = CRC32().apply { update(bytes, 0, body) }.value
        val stored = DataInputStream(bytes.inputStream(body, 8)).readLong()
        if (crc != stored) return null
        DataInputStream(bytes.inputStream(0, body)).use { inp ->
            val magic = ByteArray(4).also { inp.readFully(it) }
            if (!magic.contentEquals(MAGIC)) return null
            val h = IntArray(inp.readInt()) { inp.readInt() }
            if (!h.contentEquals(header)) return null
            List(inp.readInt()) {
                val frame = inp.readInt()
                frame to ByteArray(inp.readInt()).also { inp.readFully(it) }
            }
        }
    }.getOrNull()

    private fun atomicWrite(f: File, data: ByteArray) {
        val tmp = File(f.path + ".tmp")
        tmp.writeBytes(data)
        if (!tmp.renameTo(f)) { f.delete(); tmp.renameTo(f) }
    }

    companion object {
        const val VERSION = 1
        const val CAP_BYTES = 2L * 1024 * 1024 * 1024
        private val MAGIC = "VSCP".toByteArray()
    }
}
