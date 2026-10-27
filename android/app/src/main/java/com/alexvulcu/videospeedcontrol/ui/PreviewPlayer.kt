package com.alexvulcu.videospeedcontrol.ui

import android.content.Context
import androidx.annotation.OptIn
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.SeekParameters
import com.alexvulcu.videospeedcontrol.core.Timing
import com.alexvulcu.videospeedcontrol.core.Piece
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Play preview: the source file played with the export's timing. Each piece (section or the
 * rest) lasts 1/rate per frame, so the player speed is rate ÷ file fps, switched at the piece
 * borders (accurate to a frame or two – it is a preview). The pitch is the slow-mo factor:
 * phone slow-mo sound comes back to its real pitch at every speed, as in the export.
 * With sections the preview is silent: the player's clock is the sound, and a speed change only
 * reaches sound that is not buffered yet (~1 s later), so the picture would run on at the old
 * speed. Without sound the clock follows the speed at once. (The desktop preview is silent too.)
 * Desktop counterpart: `playback.PlayPlan` + `workers.Player`.
 */
@OptIn(UnstableApi::class)
class PreviewPlayer(context: Context, private val scope: CoroutineScope) {
    val player: ExoPlayer = ExoPlayer.Builder(context).build().apply {
        setSeekParameters(SeekParameters.EXACT)
        repeatMode = Player.REPEAT_MODE_OFF
    }
    private var poll: Job? = null
    private var loadedUri: android.net.Uri? = null

    val isPlaying get() = poll?.isActive == true

    /** Play [job] from source frame [from]; [onFrame] gets the frame shown, [onEnd] at the trim end. */
    fun play(job: Timing, from: Int, onFrame: (Int) -> Unit, onEnd: () -> Unit) {
        stop()
        val info = job.info
        val fm = info.frames
        val pieces = job.pieces()
        val start = if (from in job.trim.start until job.trimEnd - 1) from else job.trim.start
        val pitch = (info.realFps / info.fps).toDouble().toFloat()
        val t0 = fm.ptsUs[0]
        val endUs = if (job.trimEnd < fm.count) fm.ptsUs[job.trimEnd] else Long.MAX_VALUE

        if (loadedUri != info.uri) {
            player.setMediaItem(MediaItem.fromUri(info.uri))
            player.prepare()
            loadedUri = info.uri
        }
        val withSound = !job.hasSegments
        player.trackSelectionParameters = player.trackSelectionParameters.buildUpon()
            .setTrackTypeDisabled(C.TRACK_TYPE_AUDIO, !withSound).build()
        player.seekTo((fm.ptsUs[start] - t0) / 1000)
        var current: Piece? = null
        fun apply(p: Piece) {
            if (p == current) return
            current = p
            player.playbackParameters = PlaybackParameters((p.rate / info.fps).toDouble().toFloat(), pitch)
        }
        apply(pieces.first { start < it.end })
        player.play()

        poll = scope.launch {
            while (isActive) {
                val us = player.currentPosition * 1000 + t0
                var f = fm.ptsUs.binarySearch(us).let { if (it < 0) -it - 2 else it }.coerceIn(0, fm.count - 1)
                if (us >= endUs || player.playbackState == Player.STATE_ENDED) {
                    player.pause()
                    onFrame(minOf(f, job.trimEnd - 1))
                    onEnd()
                    break
                }
                f = maxOf(f, start)
                pieces.firstOrNull { f < it.end }?.let(::apply)
                onFrame(f)
                delay(16)
            }
        }
    }

    fun stop() {
        poll?.cancel()
        poll = null
        player.pause()
    }

    fun release() {
        stop()
        player.release()
    }
}
