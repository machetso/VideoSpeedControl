package com.alexvulcu.videospeedcontrol.core

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.MediaStore
import org.json.JSONObject

/**
 * The folder for clip speed treatments (user, 0.93): Documents/VideoSpeedControl/Clip Speed
 * Treatments/. "Save" writes there directly (an existing file of the same name is replaced);
 * the previews of videos with a .cst there are kept by the preview clean-up.
 */
class CstStore(private val context: Context) {
    private val collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)

    /** Saves [text] as [name]; returns the file's uri. */
    fun save(name: String, text: String): Uri {
        val uri = find(name) ?: context.contentResolver.insert(collection, ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, "application/octet-stream")
            put(MediaStore.MediaColumns.RELATIVE_PATH, RELATIVE_PATH)
        }) ?: error("Can't create $name in $RELATIVE_PATH")
        context.contentResolver.openOutputStream(uri, "wt")!!.use { it.write(text.toByteArray()) }
        return uri
    }

    /** Fingerprints of the videos that have a .cst in the folder (files this app can read). */
    fun fingerprints(): Set<String> {
        val out = HashSet<String>()
        query(null) { uri, _ ->
            runCatching {
                val text = context.contentResolver.openInputStream(uri)!!.use { it.readBytes().decodeToString() }
                out += JSONObject(text).getJSONObject("source").getString("fingerprint")
            }
        }
        return out
    }

    private fun find(name: String): Uri? {
        var found: Uri? = null
        query(name) { uri, _ -> if (found == null) found = uri }
        return found
    }

    private fun query(name: String?, each: (Uri, String) -> Unit) {
        val sel = "${MediaStore.MediaColumns.RELATIVE_PATH} = ?" + if (name != null) " AND ${MediaStore.MediaColumns.DISPLAY_NAME} = ?" else ""
        val args = listOfNotNull(RELATIVE_PATH, name).toTypedArray()
        context.contentResolver.query(collection, arrayOf(MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DISPLAY_NAME),
            sel, args, null)?.use { c ->
            while (c.moveToNext()) {
                val n = c.getString(1) ?: continue
                if (name == null && !n.endsWith(Treatment.SUFFIX)) continue
                each(android.content.ContentUris.withAppendedId(collection, c.getLong(0)), n)
            }
        }
    }

    companion object {
        const val RELATIVE_PATH = "Documents/VideoSpeedControl/Clip Speed Treatments/"

        /** The folder in the system file picker ("Load" starts there). */
        val folderUri: Uri = DocumentsContract.buildDocumentUri("com.android.externalstorage.documents",
            "primary:" + RELATIVE_PATH.trimEnd('/'))
    }
}
