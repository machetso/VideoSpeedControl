package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import android.os.ParcelFileDescriptor
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.inspector.MediaExtractorCompat
import java.io.IOException
import java.nio.ByteBuffer

/**
 * Drop-in for [MediaExtractor] (same calls, same SEEK_ / SAMPLE_FLAG_ constants) that also reads
 * files Android's own extractor can't (user request 2026-11-03: old AVI / DivX / Xvid videos).
 * [setDataSource] tries Android's extractor first – it is what every other file was tested
 * with – and falls back to Media3's extractors (AVI, and whatever else Media3 reads) when
 * Android refuses the file or finds no track in it.
 *
 * Media3 gets content:// links (folder / file picker, MediaStore) as an open file
 * (/proc/self/fd/N): through the content link it found the tracks of the user's DivX AVIs but
 * read no frames at all ("contains no video frames", 2026-11-04).
 */
@OptIn(UnstableApi::class)
class Extractor {
    private var android: MediaExtractor? = null
    private var media3: MediaExtractorCompat? = null
    private var media3File: ParcelFileDescriptor? = null

    /** True when Media3 reads the file (Android's extractor could not). */
    val usesMedia3: Boolean get() = media3 != null

    fun setDataSource(context: Context, uri: Uri, headers: Map<String, String>?) {
        release()
        val ex = MediaExtractor()
        val first = try {
            ex.setDataSource(context, uri, headers)
            if (ex.trackCount > 0) { android = ex; return }
            null
        } catch (e: IOException) {
            e
        } catch (e: IllegalArgumentException) {
            e
        }
        ex.release()
        val m3 = MediaExtractorCompat(context)
        var pfd: ParcelFileDescriptor? = null
        try {
            var source = uri
            if (uri.scheme == "content") {
                pfd = context.contentResolver.openFileDescriptor(uri, "r") ?: throw IOException("can't open $uri")
                source = Uri.fromFile(java.io.File("/proc/self/fd/${pfd.fd}"))
            }
            m3.setDataSource(context, source, headers)
            if (m3.trackCount == 0) throw IOException("no tracks")
        } catch (e: Exception) {
            m3.release()
            pfd?.close()
            throw IOException("This file format can't be read" +
                (first?.message?.let { " ($it)" } ?: ""), e)
        }
        media3 = m3
        media3File = pfd
    }

    private val a: MediaExtractor? get() = android
    private fun m(): MediaExtractorCompat = media3 ?: throw IllegalStateException("No data source set")

    val trackCount: Int get() = a?.trackCount ?: m().trackCount
    fun getTrackFormat(index: Int): MediaFormat = a?.getTrackFormat(index) ?: m().getTrackFormat(index)
    fun selectTrack(index: Int) { a?.selectTrack(index) ?: m().selectTrack(index) }
    fun unselectTrack(index: Int) { a?.unselectTrack(index) ?: m().unselectTrack(index) }
    /** [mode]: MediaExtractor.SEEK_TO_* (Media3 uses the same values). */
    fun seekTo(timeUs: Long, mode: Int) { a?.seekTo(timeUs, mode) ?: m().seekTo(timeUs, mode) }
    fun advance(): Boolean = a?.advance() ?: m().advance()
    fun readSampleData(buffer: ByteBuffer, offset: Int): Int = a?.readSampleData(buffer, offset) ?: m().readSampleData(buffer, offset)
    val sampleTime: Long get() = a?.sampleTime ?: m().sampleTime
    val sampleFlags: Int get() = a?.sampleFlags ?: m().sampleFlags
    val sampleTrackIndex: Int get() = a?.sampleTrackIndex ?: m().sampleTrackIndex
    val sampleSize: Long get() = a?.sampleSize ?: m().sampleSize

    fun release() {
        android?.release()
        media3?.release()
        media3File?.close()
        android = null
        media3 = null
        media3File = null
    }
}
