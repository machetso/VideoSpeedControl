package com.alexvulcu.videospeedcontrol.core

import android.media.MediaCodec
import android.media.MediaFormat
import android.media.MediaMuxer
import java.io.FileDescriptor
import java.nio.ByteBuffer

/**
 * What the exports write into: Android's MediaMuxer (MP4) or the own [MkvMuxer]. Same calls as
 * MediaMuxer, so the export code does not care which one it gets.
 */
interface OutMuxer {
    fun addTrack(format: MediaFormat): Int
    fun setLocation(latitude: Float, longitude: Float) {}
    fun start()
    fun writeSampleData(track: Int, buf: ByteBuffer, info: MediaCodec.BufferInfo)
    fun stop()
    fun release()

    /**
     * Output containers of "Convert videos". MOV: Android has no QuickTime writer – the file is
     * an MP4 (ISO base media, which QuickTime / Apple devices play) with the .mov name.
     */
    enum class Container(val extension: String, val mime: String) {
        MP4("mp4", "video/mp4"), MOV("mov", "video/quicktime"), MKV("mkv", "video/x-matroska");

        companion object {
            fun of(name: String?): Container = entries.firstOrNull { it.name.equals(name, true) } ?: MP4
        }
    }

    companion object {
        fun create(fd: FileDescriptor, container: Container): OutMuxer = when (container) {
            Container.MKV -> MkvMuxer(fd)
            else -> AndroidMuxer(MediaMuxer(fd, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4))
        }

        /** Sound codecs (mime) each container takes – MediaMuxer refuses MP3 and Opus in MP4 (tested). */
        private val MP4_AUDIO = setOf(MediaFormat.MIMETYPE_AUDIO_AAC,
            MediaFormat.MIMETYPE_AUDIO_AMR_NB, MediaFormat.MIMETYPE_AUDIO_AMR_WB)

        fun canHold(container: Container, audioMime: String?): Boolean = when (container) {
            Container.MKV -> audioMime in Mkv.AUDIO_MIMES
            Container.MP4 -> audioMime in MP4_AUDIO
            Container.MOV -> audioMime == MediaFormat.MIMETYPE_AUDIO_AAC
        }

        /** Video codecs: MKV takes AV1 / HEVC / H.264; MOV (an MP4 here) not AV1 – like the desktop. */
        fun canHoldVideo(container: Container, codec: VideoCodec): Boolean =
            !(container == Container.MOV && codec.mime == MediaFormat.MIMETYPE_VIDEO_AV1)
    }
}

class AndroidMuxer(private val m: MediaMuxer) : OutMuxer {
    override fun addTrack(format: MediaFormat) = m.addTrack(format)
    override fun setLocation(latitude: Float, longitude: Float) = m.setLocation(latitude, longitude)
    override fun start() = m.start()
    override fun writeSampleData(track: Int, buf: ByteBuffer, info: MediaCodec.BufferInfo) = m.writeSampleData(track, buf, info)
    override fun stop() = m.stop()
    override fun release() = m.release()
}
