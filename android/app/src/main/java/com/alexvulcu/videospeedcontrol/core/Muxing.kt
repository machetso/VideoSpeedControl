package com.alexvulcu.videospeedcontrol.core

import android.content.Context
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.media.MediaMuxer
import java.io.FileDescriptor
import java.nio.ByteBuffer

class ExportCancelled : Exception("Export cancelled")

object Muxing {
    data class Container(val muxerFormat: Int, val extension: String, val mime: String)

    private val MP4 = Container(MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4, "mp4", "video/mp4")
    private val WEBM = Container(MediaMuxer.OutputFormat.MUXER_OUTPUT_WEBM, "webm", "video/webm")

    /** Where a stream copy of this codec can go (MediaMuxer's limits), null = nowhere. */
    fun containerFor(videoMime: String): Container? = when (videoMime) {
        MediaFormat.MIMETYPE_VIDEO_AVC, MediaFormat.MIMETYPE_VIDEO_HEVC,
        MediaFormat.MIMETYPE_VIDEO_MPEG4, MediaFormat.MIMETYPE_VIDEO_H263 -> MP4
        MediaFormat.MIMETYPE_VIDEO_AV1 -> MP4
        MediaFormat.MIMETYPE_VIDEO_VP8, MediaFormat.MIMETYPE_VIDEO_VP9 -> WEBM
        else -> null
    }
}

/**
 * Lossless retime (mode A): every video sample of the trim range is copied unchanged, only its
 * presentation time is rewritten (desktop: `-itsscale` / `setts`). With [withAudio] the sound is
 * rendered first (see [Audio]) and interleaved with the video in the same file.
 */
class LosslessExport(
    private val context: Context,
    private val job: LosslessJob,
    private val withAudio: Boolean = false,
) {
    @Volatile var cancelled = false

    /** Writes the output to [fd]; [progress] gets 0..1. Returns the number of frames written. */
    fun run(fd: FileDescriptor, progress: (Float) -> Unit = {}): Int {
        val blockers = job.blockers()
        require(blockers.isEmpty()) { "Lossless export not possible: " + blockers.joinToString("; ") }
        val info = job.info
        val audioShare = if (withAudio && info.audio != null) 0.8f else 0f
        val audio = if (audioShare > 0) {
            Audio.render(context, job, { cancelled }) { progress(it * audioShare) }
        } else null
        val videoProgress = { p: Float -> progress(audioShare + p * (1 - audioShare)) }
        val container = Muxing.containerFor(info.videoMime)!!
        val pts = info.frames.ptsUs
        val startUs = pts[job.trim.start]
        val endUs = if (job.trimEnd < pts.size) pts[job.trimEnd] else Long.MAX_VALUE
        val (times, end) = info.frames.exactTimes(info.fps)
        val retime = Segments.retimer(job.pieces(), times, end)

        val ex = MediaExtractor()
        val muxer = MediaMuxer(fd, container.muxerFormat)
        var started = false
        try {
            ex.setDataSource(context, info.uri, null)
            val track = (0 until ex.trackCount).first {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            }
            val format = ex.getTrackFormat(track)
            format.removeKey(MediaFormat.KEY_DURATION)
            muxer.setOrientationHint(info.rotation)
            location(info)?.let { (lat, lon) -> muxer.setLocation(lat, lon) }
            val outTrack = muxer.addTrack(format)
            val audioTrack = audio?.let { muxer.addTrack(it.format) } ?: -1
            muxer.start()
            started = true

            ex.selectTrack(track)
            ex.seekTo(startUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            val bufSize = maxOf(
                if (format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE) else 0,
                info.width * info.height * 2, 4 shl 20,
            )
            val buf = ByteBuffer.allocateDirect(bufSize)
            val bi = MediaCodec.BufferInfo()
            val total = job.sourceFrameCount
            var written = 0
            // audio samples are interleaved by time with the video
            var nextAudio = 0
            val abi = MediaCodec.BufferInfo()
            fun writeAudioUntil(us: Long) {
                val a = audio ?: return
                while (nextAudio < a.samples.size && a.samples[nextAudio].ptsUs <= us) {
                    val s = a.samples[nextAudio++]
                    abi.set(0, s.data.size, s.ptsUs, s.flags)
                    muxer.writeSampleData(audioTrack, ByteBuffer.wrap(s.data), abi)
                }
            }
            while (true) {
                if (cancelled) throw ExportCancelled()
                val t = ex.sampleTime
                if (t < 0) break
                val sync = ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0
                if (sync && t >= endUs) break               // trim end is a GOP boundary
                if (t in startUs until endUs) {
                    val size = ex.readSampleData(buf, 0)
                    val frame = info.frames.indexOf(t)
                    check(frame >= 0) { "Sample at $t µs is not in the frame map" }
                    val outUs = retime(frame)
                    writeAudioUntil(outUs)
                    bi.set(0, size, outUs, if (sync) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                    muxer.writeSampleData(outTrack, buf, bi)
                    written++
                    if (written % 16 == 0) videoProgress(written.toFloat() / total)
                }
                if (!ex.advance()) break
            }
            writeAudioUntil(Long.MAX_VALUE)
            progress(1f)
            return written
        } finally {
            ex.release()
            try {
                if (started) muxer.stop()
            } finally {
                muxer.release()
            }
        }
    }

    /** "+52.5200+013.4050/" (ISO 6709) from the source → (lat, lon). */
    private fun location(info: ClipInfo): Pair<Float, Float>? {
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(context, info.uri)
            val s = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_LOCATION) ?: return null
            val m = Regex("""([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)""").find(s) ?: return null
            m.groupValues[1].toFloat() to m.groupValues[2].toFloat()
        } catch (_: Exception) {
            null
        } finally {
            r.release()
        }
    }
}
