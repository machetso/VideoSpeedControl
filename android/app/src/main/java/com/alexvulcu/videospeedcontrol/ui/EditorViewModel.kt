package com.alexvulcu.videospeedcontrol.ui

import android.app.Application
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.asImageBitmap
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.alexvulcu.videospeedcontrol.core.ClipEdit
import com.alexvulcu.videospeedcontrol.core.ClipInfo
import com.alexvulcu.videospeedcontrol.core.ExportCancelled
import com.alexvulcu.videospeedcontrol.core.FrameSource
import com.alexvulcu.videospeedcontrol.core.LosslessExport
import com.alexvulcu.videospeedcontrol.core.LosslessJob
import com.alexvulcu.videospeedcontrol.core.Quality
import com.alexvulcu.videospeedcontrol.core.ReencodeExport
import com.alexvulcu.videospeedcontrol.core.ReencodeJob
import com.alexvulcu.videospeedcontrol.core.Timing
import com.alexvulcu.videospeedcontrol.core.VideoCodec
import com.alexvulcu.videospeedcontrol.core.Muxing
import com.alexvulcu.videospeedcontrol.core.OutputStore
import com.alexvulcu.videospeedcontrol.core.Probe
import com.alexvulcu.videospeedcontrol.core.Proxy
import com.alexvulcu.videospeedcontrol.core.Segments
import com.alexvulcu.videospeedcontrol.core.Segment
import com.alexvulcu.videospeedcontrol.core.Smart
import com.alexvulcu.videospeedcontrol.core.SmartExport
import com.alexvulcu.videospeedcontrol.core.SmartJob
import com.alexvulcu.videospeedcontrol.core.Rational
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

sealed interface ClipState {
    data object None : ClipState
    data object Loading : ClipState
    data class Loaded(val info: ClipInfo) : ClipState
    data class Failed(val message: String) : ClipState
}

sealed interface ExportState {
    data object Idle : ExportState
    data class Running(val progress: Float) : ExportState
    data class Done(val name: String, val uri: Uri, val frames: Int, val seconds: Double) : ExportState
    data class Failed(val message: String) : ExportState
}

class EditorViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("vsc", Context.MODE_PRIVATE)

    var clip by mutableStateOf<ClipState>(ClipState.None)
        private set
    var edit by mutableStateOf<ClipEdit?>(null)
        private set
    var playhead by mutableStateOf(0)
        private set
    var pendingStart by mutableStateOf<Int?>(null)
        private set
    var selectedSection by mutableStateOf(-1)
        private set
    /** Rate for new sections – the last one chosen (desktop: QSettings "sections/out_fps"). */
    var sectionFps by mutableStateOf(Rational.parse(prefs.getString("section_fps", "30")!!))
        private set
    var fps by mutableStateOf(Rational.parse(prefs.getString("fps", "25")!!))
        private set
    var mode by mutableStateOf(when (prefs.getString("mode", "lossless")) {
        "reencode" -> Mode.REENCODE
        "smart" -> Mode.SMART
        else -> Mode.LOSSLESS
    })
        private set
    /** Re-encode speed without sections: null = every frame once at [fps]. */
    var speed by mutableStateOf(prefs.getString("speed", "")!!.takeIf { it.isNotEmpty() }?.let(Rational::parse))
        private set
    var codec by mutableStateOf(runCatching { VideoCodec.valueOf(prefs.getString("codec", "HEVC")!!) }.getOrDefault(VideoCodec.HEVC))
        private set
    var shortSide by mutableStateOf(prefs.getInt("short_side", 0).takeIf { it > 0 })
        private set
    var quality by mutableStateOf(runCatching { Quality.valueOf(prefs.getString("quality", "HIGH")!!) }.getOrDefault(Quality.HIGH))
        private set

    enum class Mode { LOSSLESS, SMART, REENCODE }

    /** Lossless and smart cut only at keyframes. */
    val snapsToKeyframes get() = mode != Mode.REENCODE

    // ------------------------------------------------------------------ smart export

    /** Safe join keyframes of the clip (null = still being analysed). */
    var joins by mutableStateOf<List<Int>?>(null)
        private set
    var joinsError by mutableStateOf<String?>(null)
        private set
    /** "Re-encode everything that differs from the output frame rate" (stored). */
    var smartAuto by mutableStateOf(prefs.getBoolean("smart_auto", true))
        private set
    /** Ticks changed by hand, by part ("start-end-rate"); cleared when the switch is used. */
    private val smartOverride = mutableStateMapOf<String, Boolean>()

    /** One run of one playback rate in the trim range (a section or the real time between). */
    data class SmartPiece(val start: Int, val end: Int, val rate: Rational, val differs: Boolean, val reencode: Boolean) {
        val key get() = "$start-$end-$rate"
    }

    /**
     * Rule (user, 2026-10-28): a part plays at the output frame rate → copied; any other rate
     * (e.g. real time of a 240 fps recording at 25p) → re-encoded at the output frame rate.
     */
    fun smartPieces(): List<SmartPiece> {
        val e = edit ?: return emptyList()
        return Segments.pieces(e.segments, e.trim.start, e.trimEnd, e.info.realFps).map { p ->
            val differs = p.rate != fps
            val key = "${p.start}-${p.end}-${p.rate}"
            SmartPiece(p.start, p.end, p.rate, differs, smartOverride[key] ?: (smartAuto && differs))
        }
    }

    fun chooseSmartAuto(on: Boolean) {
        smartAuto = on
        smartOverride.clear()
        prefs.edit().putBoolean("smart_auto", on).apply()
    }

    fun setPieceReencode(piece: SmartPiece, on: Boolean) {
        smartOverride[piece.key] = on
    }

    private fun smartJob(e: ClipEdit): SmartJob {
        // every part becomes an explicit section – the desktop's .cst format (reencode + out_fps)
        val segs = smartPieces().map { Segment(it.start, it.end, it.rate, it.reencode, if (it.reencode) fps else null) }
        return SmartJob(e.info, fps, e.trim, segs, joins ?: emptyList(), quality)
    }

    /** The export as currently set up (timing for preview, labels and export). */
    fun job(): Timing? {
        val e = edit ?: return null
        return when (mode) {
            Mode.LOSSLESS -> e.job(fps)
            Mode.SMART -> smartJob(e)
            Mode.REENCODE -> e.reencodeJob(fps, speed, codec, shortSide, quality)
        }
    }

    fun chooseFps(r: Rational) { fps = r; prefs.edit().putString("fps", r.toString()).apply() }
    fun chooseSpeed(r: Rational?) { speed = r; prefs.edit().putString("speed", r?.toString() ?: "").apply() }
    fun chooseCodec(c: VideoCodec) { codec = c; prefs.edit().putString("codec", c.name).apply() }
    fun chooseShortSide(v: Int?) { shortSide = v; prefs.edit().putInt("short_side", v ?: 0).apply() }
    fun chooseQuality(q: Quality) { quality = q; prefs.edit().putString("quality", q.name).apply() }

    fun chooseMode(m: Mode) {
        stopPlayback()
        mode = m
        prefs.edit().putString("mode", m.name.lowercase()).apply()
        if (m != Mode.REENCODE) edit = edit?.snappedTrim()       // lossless / smart cut only at keyframes
    }
    var sound by mutableStateOf(true)
    var export by mutableStateOf<ExportState>(ExportState.Idle)
        private set

    /** Picture at the playhead; [previewExact] = false while only a thumbnail is shown. */
    var preview by mutableStateOf<Bitmap?>(null)
        private set
    var previewExact by mutableStateOf(false)
        private set
    val thumbs = mutableStateListOf<Thumb>()

    /** Small picture of every frame (frame-accurate scrubbing, play preview); fills while built. */
    private var proxy: Proxy? = null
    var proxyProgress by mutableStateOf(0f)
        private set
    private var proxyJob: Job? = null
    private var proxyPlay: Job? = null
    /** Play preview shows the ExoPlayer surface (constant speed with sound) instead of frames. */
    var playingVideo by mutableStateOf(false)
        private set
    /** Magnetic cursor (desktop 🧲, stored). */
    var magnet by mutableStateOf(prefs.getBoolean("magnet", true))
        private set

    private var source: FrameSource? = null
    private var frameJob: Job? = null
    private var thumbJob: Job? = null
    private var cancelRunning: (() -> Unit)? = null
    private var player: PreviewPlayer? = null

    /** Play preview running (the preview pane shows the player instead of the frame). */
    var playing by mutableStateOf(false)
        private set
    val previewPlayer: PreviewPlayer
        get() = player ?: PreviewPlayer(getApplication(), viewModelScope).also { player = it }

    fun open(uri: Uri) {
        stopPlayback()
        player?.release()
        player = null
        clip = ClipState.Loading
        export = ExportState.Idle
        closeSource()
        edit = null
        viewModelScope.launch {
            try {
                val info = withContext(Dispatchers.IO) { Probe.probe(getApplication(), uri) }
                clip = ClipState.Loaded(info)
                edit = ClipEdit(info)
                playhead = 0
                pendingStart = null
                selectedSection = -1
                source = withContext(Dispatchers.IO) { FrameSource(getApplication(), info) }
                loadThumbs()
                loadProxy(info)
                loadJoins(info)
                seek(0)
            } catch (e: Exception) {
                clip = ClipState.Failed(e.message ?: e.toString())
            }
        }
    }

    private fun loadThumbs() {
        val src = source ?: return
        thumbJob = viewModelScope.launch {
            src.thumbnails(max = 60, width = 192) { frame, bmp ->
                val t = Thumb(frame, bmp.asImageBitmap(), bmp)
                viewModelScope.launch {
                    val i = thumbs.indexOfFirst { it.frame > frame }.let { if (it < 0) thumbs.size else it }
                    thumbs.add(i, t)
                    if (!previewExact && preview == null) preview = bmp
                }
            }
        }
    }

    private fun loadJoins(info: ClipInfo) {
        joins = null
        joinsError = null
        smartOverride.clear()
        viewModelScope.launch {
            try {
                joins = withContext(Dispatchers.IO) { Smart.joinPoints(getApplication(), info) }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                joins = emptyList()
                joinsError = e.message ?: e.toString()
            }
        }
    }

    private fun loadProxy(info: ClipInfo) {
        proxyProgress = 0f
        proxyJob = viewModelScope.launch {
            try {
                Proxy.build(getApplication(), info) { p ->
                    proxy = p
                    viewModelScope.launch { proxyProgress = p.fraction }
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.w("Vsc", "proxy failed", e)    // scrubbing falls back to thumbnails
            }
        }
    }

    // ------------------------------------------------------------------ playhead

    /** Move the playhead: nearest thumbnail at once, the exact frame after 120 ms of rest. */
    fun seek(frame: Int) {
        stopPlayback()
        val e = edit ?: return
        val f = frame.coerceIn(0, e.info.frames.count - 1)
        playhead = f
        selectedSection = e.sectionAt(f)
        frameJob?.cancel()
        val quick = proxy?.takeIf { it.has(f) }?.bitmap(f)
        if (quick != null) {
            preview = quick
            previewExact = false
        } else thumbs.lastOrNull { it.frame <= f }?.let { t ->
            preview = t.bitmap
            previewExact = t.frame == f
        }
        val src = source ?: return
        frameJob = viewModelScope.launch {
            delay(120)
            val bmp = src.frame(f, 1080) ?: return@launch
            if (playhead == f) {
                preview = bmp
                previewExact = true
            }
        }
    }

    fun step(delta: Int) = seek(playhead + delta)

    /** Timeline tap / drag: with the magnet on, snaps to section borders within [radius] frames. */
    fun seekFromTimeline(frame: Int, radius: Int) {
        val e = edit ?: return
        seek(if (magnet) e.snap(frame, radius, pendingStart) else frame)
    }

    fun toggleMagnet() {
        magnet = !magnet
        prefs.edit().putBoolean("magnet", magnet).apply()
    }

    fun previousKeyframe() {
        val e = edit ?: return
        seek(e.info.frames.keyframeAtOrBefore(maxOf(0, playhead - 1)))
    }

    fun nextKeyframe() {
        val e = edit ?: return
        seek(minOf(e.info.frames.keyframeAfter(playhead), e.info.frames.count - 1))
    }

    // ------------------------------------------------------------------ play preview

    /**
     * Play preview. Constant speed the decoder can keep up with (≤ 2× the file rate): ExoPlayer
     * with sound. Sections or fast real-time parts of slow-mo clips: proxy frames drawn on an
     * exact clock (smooth at any speed, borders on the frame, silent) – ExoPlayer would drop
     * frames decoding 120–240 full-size frames per second.
     */
    fun togglePlay() {
        if (playing) {
            stopPlayback()
            seek(playhead)
            return
        }
        val e = edit ?: return
        val job = job() ?: return
        val fast = (job.pieces().maxOf { it.rate } / e.info.fps).toDouble() > 2.0
        val p = proxy
        playing = true
        frameJob?.cancel()
        if ((job.hasSegments || fast) && p != null && p.complete) {
            playProxy(job, p)
        } else {
            playingVideo = true
            previewPlayer.play(job, playhead,
                onFrame = { f ->
                    playhead = f
                    selectedSection = e.sectionAt(f)
                },
                onEnd = {
                    playing = false
                    playingVideo = false
                    seek(playhead)
                })
        }
    }

    private fun playProxy(job: Timing, p: Proxy) {
        val ps = job.pieces()
        val from = if (playhead in job.trim.start until job.trimEnd - 1) playhead else job.trim.start
        val t0 = Segments.outputTime(ps, from).toDouble()
        val dur = Segments.duration(ps).toDouble()
        proxyPlay = viewModelScope.launch {
            val n0 = System.nanoTime()
            var shown = -1
            while (true) {
                val t = t0 + (System.nanoTime() - n0) / 1e9
                if (t >= dur) break
                val f = Segments.sourceFrame(ps, t)
                if (f != shown) {
                    shown = f
                    p.bitmap(f)?.let { preview = it }
                    previewExact = false
                    playhead = f
                    selectedSection = job.segments.indexOfFirst { f >= it.start && f < it.end }
                }
                delay(4)
            }
            playing = false
            seek(playhead)
        }
    }

    private fun stopPlayback() {
        if (!playing) return
        playing = false
        playingVideo = false
        proxyPlay?.cancel()
        proxyPlay = null
        player?.stop()
    }

    // ------------------------------------------------------------------ sections

    fun markStart() {
        pendingStart = playhead
    }

    fun markEnd() {
        val start = pendingStart ?: return
        edit = edit?.addSection(start, playhead, sectionFps)
        pendingStart = null
        selectedSection = edit?.sectionAt(playhead) ?: -1
    }

    fun cancelMark() {
        pendingStart = null
    }

    fun chooseSectionFps(r: Rational) {
        sectionFps = r
        prefs.edit().putString("section_fps", r.toString()).apply()
    }

    fun setSectionFps(index: Int, r: Rational) {
        stopPlayback()
        edit = edit?.setSectionFps(index, r)
        chooseSectionFps(r)
    }

    fun removeSection(index: Int) {
        stopPlayback()
        edit = edit?.removeSection(index)
        selectedSection = -1
    }

    fun clearSections() {
        stopPlayback()
        edit = edit?.clearSections()
        selectedSection = -1
    }

    fun undo() {
        stopPlayback()
        edit = edit?.undo()
        selectedSection = edit?.sectionAt(playhead) ?: -1
    }

    fun redo() {
        stopPlayback()
        edit = edit?.redo()
        selectedSection = edit?.sectionAt(playhead) ?: -1
    }

    // ------------------------------------------------------------------ trim

    fun setIn() {
        edit = edit?.withIn(playhead, snap = snapsToKeyframes)
        edit?.let { seek(it.trim.start) }
    }

    fun setOut() {
        stopPlayback()
        edit = edit?.withOut(playhead, snap = snapsToKeyframes)
    }

    fun clearTrim() {
        stopPlayback()
        edit = edit?.clearTrim()
    }

    // ------------------------------------------------------------------ export

    fun startExport() {
        stopPlayback()
        val e = edit ?: return
        if (export is ExportState.Running) return
        val job = job() ?: return
        val blockers = when (job) {
            is LosslessJob -> job.blockers()
            is SmartJob -> if (joins == null) listOf("The keyframes of this clip are still being analysed") else job.blockers()
            is ReencodeJob -> job.blockers()
            else -> emptyList()
        }
        if (blockers.isNotEmpty()) {
            export = ExportState.Failed(blockers.joinToString("\n"))
            return
        }
        val ext: String
        val mime: String
        val run: (java.io.FileDescriptor, (Float) -> Unit) -> Int
        when (job) {
            is LosslessJob -> {
                val c = Muxing.containerFor(e.info.videoMime)!!
                ext = c.extension; mime = c.mime
                val x = LosslessExport(getApplication(), job, withAudio = sound)
                cancelRunning = { x.cancelled = true }
                run = { fd, p -> x.run(fd, p) }
            }
            is SmartJob -> {
                ext = "mp4"; mime = "video/mp4"
                val x = SmartExport(getApplication(), job, withAudio = sound)
                cancelRunning = { x.cancelled = true }
                run = { fd, p -> x.run(fd, p) }
            }
            else -> {
                ext = "mp4"; mime = "video/mp4"
                val x = ReencodeExport(getApplication(), job as ReencodeJob, withAudio = sound)
                cancelRunning = { x.cancelled = true }
                run = { fd, p -> x.run(fd, p) }
            }
        }
        export = ExportState.Running(0f)
        viewModelScope.launch {
            val store = OutputStore(getApplication())
            export = withContext(Dispatchers.IO) {
                val out = store.create(job.fileStem(), ext, mime)
                val t0 = System.nanoTime()
                try {
                    val frames = store.open(out).use { pfd ->
                        run(pfd.fileDescriptor) { p -> export = ExportState.Running(p) }
                    }
                    store.publish(out)
                    ExportState.Done(out.displayName, out.uri, frames, (System.nanoTime() - t0) / 1e9)
                } catch (ex: Exception) {
                    store.discard(out)
                    if (ex is ExportCancelled) ExportState.Idle else ExportState.Failed(ex.message ?: ex.toString())
                }
            }
            cancelRunning = null
        }
    }

    fun cancelExport() {
        cancelRunning?.invoke()
    }

    private fun closeSource() {
        frameJob?.cancel()
        proxyJob?.cancel()
        proxy = null
        proxyProgress = 0f
        thumbJob?.cancel()
        thumbs.clear()
        preview = null
        previewExact = false
        val s = source ?: return
        source = null
        viewModelScope.launch { s.release() }
    }

    override fun onCleared() {
        player?.release()
        source?.close()
    }
}
