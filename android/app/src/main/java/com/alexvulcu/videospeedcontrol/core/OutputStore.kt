package com.alexvulcu.videospeedcontrol.core

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.MediaStore

/**
 * Output files in Movies/VideoSpeedControl/ via MediaStore, so they appear in Google Photos.
 * A file stays "pending" (hidden) until [publish]; [discard] removes incomplete outputs, like the
 * desktop deletes them after a cancel or failure.
 */
class OutputStore(private val context: Context) {
    data class Output(val uri: Uri, val displayName: String)

    private val collection = MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)

    /** Creates "<stem>.<ext>" in [folder]; an existing name gets "_2", "_3" … (desktop policy "rename"). */
    fun create(stem: String, extension: String, mime: String, folder: String = RELATIVE_PATH): Output {
        var name = "$stem.$extension"
        var n = 2
        while (exists(name, folder)) name = "${stem}_${n++}.$extension"
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, name)
            put(MediaStore.Video.Media.MIME_TYPE, mime)
            put(MediaStore.Video.Media.RELATIVE_PATH, folder)
            put(MediaStore.Video.Media.IS_PENDING, 1)
        }
        val uri = context.contentResolver.insert(collection, values)
            ?: error("Can't create $name in $folder")
        return Output(uri, name)
    }

    fun open(out: Output): ParcelFileDescriptor =
        context.contentResolver.openFileDescriptor(out.uri, "rw") ?: error("Can't open ${out.displayName}")

    fun publish(out: Output) {
        context.contentResolver.update(
            out.uri, ContentValues().apply { put(MediaStore.Video.Media.IS_PENDING, 0) }, null, null,
        )
    }

    fun discard(out: Output) {
        runCatching { context.contentResolver.delete(out.uri, null, null) }
    }

    private fun exists(name: String, folder: String): Boolean {
        val bundle = android.os.Bundle().apply {
            putString(android.content.ContentResolver.QUERY_ARG_SQL_SELECTION,
                "${MediaStore.Video.Media.DISPLAY_NAME} = ? AND ${MediaStore.Video.Media.RELATIVE_PATH} = ?")
            putStringArray(android.content.ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS,
                arrayOf(name, folder))
            putInt(MediaStore.QUERY_ARG_MATCH_PENDING, MediaStore.MATCH_INCLUDE)
        }
        context.contentResolver.query(collection, arrayOf(MediaStore.Video.Media._ID), bundle, null)
            ?.use { return it.count > 0 }
        return false
    }

    companion object {
        const val RELATIVE_PATH = "Movies/VideoSpeedControl/"
    }
}
