package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.net.Uri
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.channels.FileChannel

/**
 * Reads QuickTime "mdta" metadata (keys + ilst) straight from an MP4 / MOV file.
 * MediaMetadataRetriever only reports com.android.capture.fps when it is stored exactly as a
 * phone writes it (float32 in moov/meta); FFmpeg – and so the desktop app's exports – write it as
 * text, possibly in moov/udta/meta. The desktop reads both, so this does too.
 */
object Mp4Meta {
    private const val MAX_MOOV = 64L shl 20

    /** All mdta tags as strings (floats formatted like FFmpeg: "120.000000"). */
    fun tags(context: Context, uri: Uri): Map<String, String> {
        val pfd = context.contentResolver.openFileDescriptor(uri, "r") ?: return emptyMap()
        pfd.use {
            FileInputStream(it.fileDescriptor).channel.use { ch -> return tags(ch) }
        }
    }

    fun tags(ch: FileChannel): Map<String, String> {
        val moov = topLevel(ch, "moov") ?: return emptyMap()
        val out = LinkedHashMap<String, String>()
        for (meta in listOfNotNull(child(moov, "meta"), child(moov, "udta")?.let { child(it, "meta") })) {
            parseMeta(meta, out)
        }
        return out
    }

    /** Body of the first top-level atom [kind], read into memory (moov is small). */
    private fun topLevel(ch: FileChannel, kind: String): ByteBuffer? {
        var pos = 0L
        val head = ByteBuffer.allocate(16)
        val size = ch.size()
        while (pos + 8 <= size) {
            head.clear().limit(16)
            ch.read(head, pos)
            head.flip()
            if (head.remaining() < 8) return null
            var len = head.getInt().toLong() and 0xffffffffL
            val type = fourcc(head)
            var header = 8
            if (len == 1L && head.remaining() >= 8) { len = head.getLong(); header = 16 }
            if (len == 0L) len = size - pos
            if (len < header) return null
            if (type == kind) {
                if (len - header > MAX_MOOV) return null
                val body = ByteBuffer.allocate((len - header).toInt())
                ch.read(body, pos + header)
                body.flip()
                return body
            }
            pos += len
        }
        return null
    }

    /** Body of the first child atom [kind] inside [parent] (a body buffer). */
    private fun child(parent: ByteBuffer, kind: String): ByteBuffer? {
        val b = parent.duplicate()
        while (b.remaining() >= 8) {
            val start = b.position()
            val len = b.getInt().toLong() and 0xffffffffL
            val type = fourcc(b)
            if (len < 8 || start + len > b.limit()) return null
            if (type == kind) {
                var bodyStart = start + 8
                // a full-box 'meta' (QuickTime in udta: version/flags first) has 4 more bytes
                if (kind == "meta" && b.getInt(bodyStart) == 0) bodyStart += 4
                return b.duplicate().apply { position(bodyStart); limit((start + len).toInt()) }.slice()
            }
            b.position((start + len).toInt())
        }
        return null
    }

    private fun parseMeta(meta: ByteBuffer, out: MutableMap<String, String>) {
        val keys = child(meta, "keys") ?: return
        val ilst = child(meta, "ilst") ?: return
        keys.position(4)                                     // version + flags
        val count = keys.getInt()
        val names = ArrayList<String>()
        repeat(count) {
            if (keys.remaining() < 8) return
            val len = keys.getInt()
            keys.getInt()                                    // namespace ("mdta")
            val bytes = ByteArray(len - 8).also { keys.get(it) }
            names += String(bytes, Charsets.UTF_8)
        }
        val b = ilst.duplicate()
        while (b.remaining() >= 8) {
            val start = b.position()
            val len = b.getInt()
            val index = b.getInt()                           // 1-based key index
            if (len < 8 || start + len > b.limit()) return
            val item = b.duplicate().apply { limit(start + len) }
            child(item.slice(), "data")?.let { data ->
                val type = data.getInt(0) and 0xffffff
                val value = data.duplicate().apply { position(8) }.slice()
                val text = when (type) {
                    1 -> String(ByteArray(value.remaining()).also { value.get(it) }, Charsets.UTF_8)
                    23 -> if (value.remaining() >= 4) String.format(java.util.Locale.US, "%f", value.getFloat()) else null
                    24 -> if (value.remaining() >= 8) String.format(java.util.Locale.US, "%f", value.getDouble()) else null
                    else -> null
                }
                if (text != null && index in 1..names.size) out.putIfAbsent(names[index - 1], text)
            }
            b.position(start + len)
        }
    }

    private fun fourcc(b: ByteBuffer) = String(ByteArray(4).also { b.get(it) }, Charsets.ISO_8859_1)
}
