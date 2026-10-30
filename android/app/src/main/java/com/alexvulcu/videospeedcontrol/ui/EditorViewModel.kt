package com.alexvulcu.videospeedcontrol.ui

import android.app.Application
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
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
import com.alexvulcu.videospeedcontrol.core.Encoders
import com.alexvulcu.videospeedcontrol.core.Muxing
import com.alexvulcu.videospeedcontrol.core.OutputStore
import com.alexvulcu.videospeedcontrol.core.Probe
import com.alexvulcu.videospeedcontrol.core.Proxy
import com.alexvulcu.videospeedcontrol.core.PreviewCache
import com.alexvulcu.videospeedcontrol.core.CstStore
import com.alexvulcu.videospeedcontrol.core.Segments
import com.alexvulcu.videospeedcontrol.core.Segment
import com.alexvulcu.videospeedcontrol.core.Trim
import com.alexvulcu.videospeedcontrol.core.rampedSegments
import com.alexvulcu.videospeedcontrol.core.Smart
import com.alexvulcu.videospeedcontrol.core.SmartExport
import com.alexvulcu.videospeedcontrol.core.SmartJob
import com.alexvulcu.videospeedcontrol.core.ExportTask
import com.alexvulcu.videospeedcontrol.core.Treatment
import com.alexvulcu.videospeedcontrol.export.ExportManager
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
    /** Codecs this phone can encode (AV1 needs an encoder, HEVC / H.264 are always there). */
    val codecs: List<VideoCodec> = VideoCodec.entries.filter { Encoders.available(it) }
    /** Re-encode codec; AV1 fast is the default (user, v0.92 – also replaces an older stored choice once). */
    var codec by mutableStateOf(run {
        val default = if (VideoCodec.AV1_FAST in codecs) VideoCodec.AV1_FAST else VideoCodec.HEVC
        if (!prefs.getBoolean("codec_default_v092", false)) {
            prefs.edit().putBoolean("codec_default_v092", true).putString("codec", default.name).apply()
        }
        runCatching { VideoCodec.valueOf(prefs.getString("codec", default.name)!!) }.getOrDefault(default)
            .takeIf { it in codecs } ?: default
    })
        private set
    var shortSide by mutableStateOf(prefs.getInt("short_side", 0).takeIf { it > 0 })
        private set
    var quality by mutableStateOf(runCatching { Quality.valueOf(prefs.getString("quality", "HIGH")!!) }.getOrDefault(Quality.HIGH))
        private set

    /** Easy (default): no codec / quality choice – re-encode AV1 fast, smart the source codec, quality High. */
    var easy by mutableStateOf(!prefs.getBoolean("pro", false))
        private set
    val defaultCodec: VideoCodec get() = if (VideoCodec.AV1_FAST in codecs) VideoCodec.AV1_FAST else VideoCodec.HEVC
    /** What the export uses (Easy ignores the Pro choices). */
    val usedCodec: VideoCodec get() = if (easy) defaultCodec else codec
    val usedQuality: Quality get() = if (easy) Quality.HIGH else quality
    /** Re-encode speed without sections: Easy has no speed choice (every frame once). */
    val usedSpeed: Rational? get() = if (easy) null else speed

    /**
     * Easy "Whole clip": the sections are set aside and the whole clip plays at [wholeRate]
     * (one section over the whole clip – works the same in every export mode).
     */
    val wholeClip: Boolean get() = edit?.whole != null
    /** Rate of the whole clip (set to the output frame rate – every recorded frame once – when switched on). */
    val wholeRate: Rational? get() = edit?.whole

    /** Whole clip on / off – undoable (the sections are kept either way). */
    fun chooseWholeClip(on: Boolean) {
        stopPlayback()
        selectedSection = -1
        pendingStart = null
        edit = edit?.withWhole(if (on) fps else null, if (on) "Whole clip" else "Back to the clip sections")
    }

    fun chooseWholeRate(r: Rational) {
        stopPlayback()
        edit = edit?.withWhole(r, "Whole clip speed")
    }

    /** The sections as exported: Easy smooths every speed change (no switches), Pro as set. */
    fun usedSegments(e: ClipEdit): List<Segment> = when {
        easy && wholeClip -> listOf(Segment(0, e.info.frames.count, wholeRate ?: fps))
        easy -> Segments.allSmooth(e.segments)
        else -> e.segments
    }

    /** The edit as the timeline shows it (Whole clip: one band over everything). */
    fun shownEdit(e: ClipEdit): ClipEdit = if (easy && wholeClip) e.copy(segments = usedSegments(e)) else e

    /** Real-time seconds from the clip start to the start of [frame] (Easy in / out display). */
    fun realSeconds(e: ClipEdit, frame: Int): Double {
        val pts = e.info.frames.ptsUs
        val us = if (frame < pts.size) pts[frame] - pts[0]
        else pts.last() - pts[0] + (pts.last() - pts[maxOf(0, pts.size - 2)])
        return us / 1e6 / (e.info.realFps / e.info.fps).toDouble()
    }

    fun chooseEasy(on: Boolean) {
        easy = on
        prefs.edit().putBoolean("pro", !on).apply()
    }

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
        return Segments.pieces(usedSegments(e), e.trim.start, e.trimEnd, e.info.realFps).map { p ->
            val differs = p.rate != fps
            val key = "${p.start}-${p.end}-${p.rate}"
            // Easy: always the automatic rule (no switch, no ticks)
            SmartPiece(p.start, p.end, p.rate, differs, if (easy) differs else smartOverride[key] ?: (smartAuto && differs))
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

    /**
     * Every part as an explicit section – the desktop's .cst format (reencode + out_fps); the
     * smooth borders of the sections are kept on the parts (the ramps are computed from them).
     */
    private fun smartParts(e: ClipEdit): List<Segment> {
        val smooth = Segments.smoothBorders(usedSegments(e))
        return smartPieces().map {
            Segment(it.start, it.end, it.rate, it.reencode, if (it.reencode) fps else null,
                smoothStart = it.start in smooth, smoothEnd = it.end in smooth)
        }
    }

    private fun smartJob(e: ClipEdit): SmartJob =
        SmartJob(e.info, fps, e.trim, rampedSegments(smartParts(e), e.trim, e.info, fps), joins ?: emptyList(), usedQuality)

    /** The export as currently set up (timing for preview, labels and export). */
    fun job(): Timing? {
        val e = edit ?: return null
        return when (mode) {
            Mode.LOSSLESS -> e.copy(segments = usedSegments(e)).job(fps)
            Mode.SMART -> smartJob(e)
            Mode.REENCODE -> e.copy(segments = usedSegments(e)).reencodeJob(fps, usedSpeed, usedCodec, shortSide, usedQuality)
        }
    }

    fun chooseFps(r: Rational) { fps = r; prefs.edit().putString("fps", r.toString()).apply() }
    fun chooseSpeed(r: Rational?) { speed = r; prefs.edit().putString("speed", r?.toString() ?: "").apply() }
    fun chooseCodec(c: VideoCodec) { codec = c; prefs.edit().putString("codec", c.name).apply() }
    fun chooseShortSide(v: Int?) { shortSide = v; prefs.edit().putInt("short_side", v ?: 0).apply() }
    fun chooseQuality(q: Quality) { quality = q; prefs.edit().putString("quality", q.name).apply() }

    fun chooseMode(m: Mode) {
        stopPlayback()
        // smart: the parts that differ from the output frame rate start out ticked (user, v0.92);
        // smart → re-encode: back to the default codec, AV1 fast
        if (m == Mode.SMART && mode != Mode.SMART) chooseSmartAuto(true)
        if (m == Mode.REENCODE && mode == Mode.SMART) chooseCodec(defaultCodec)
        mode = m
        prefs.edit().putString("mode", m.name.lowercase()).apply()
        if (m != Mode.REENCODE) edit = edit?.snappedTrim()       // lossless / smart cut only at keyframes
    }
    var sound by mutableStateOf(true)
    var export by mutableStateOf<ExportState>(ExportState.Idle)
        private set
    /** Batch list entries (from ExportManager, persisted). */
    var batch by mutableStateOf<List<ExportManager.Entry>>(emptyList())
        private set
    /** Batch entry currently loaded in the editor ("Update batch entry"). */
    var editingEntry by mutableStateOf<Long?>(null)
        private set
    /** Message for the user (treatment loaded / refused, …); null = none. */
    var message by mutableStateOf<String?>(null)
    private var pendingTreatment: Treatment.Data? = null
    /** Trim + sections last put into the batch list / exported (or as loaded). */
    private var committed by mutableStateOf<Pair<Trim, List<Segment>>?>(null)

    /** The clip has sections / a trim that are neither in the batch list nor exported. */
    val hasUnsavedWork: Boolean
        get() = edit?.let { e -> (e.trim to e.segments) != committed && (e.segments.isNotEmpty() || e.trim != Trim()) } ?: false
    private var fingerprint: String? = null

    /** Stored previews (proxy chunks, thumbnails, keyframe analysis) – 0.93. */
    private val previews = PreviewCache(app)

    init {
        ExportManager.init(app)
        schedulePreviewCleanup()
        viewModelScope.launch {
            ExportManager.entries.collect { list ->
                batch = list.filter { it.inBatch }
                val single = list.lastOrNull { !it.inBatch }
                export = when (single?.status) {
                    null, ExportManager.Status.IDLE, ExportManager.Status.CANCELLED -> ExportState.Idle
                    ExportManager.Status.WAITING -> ExportState.Running(0f)
                    ExportManager.Status.RUNNING -> ExportState.Running(single.progress)
                    ExportManager.Status.DONE -> ExportState.Done(single.output ?: "", single.outputUri ?: Uri.EMPTY,
                        single.frames, single.seconds)
                    ExportManager.Status.FAILED -> ExportState.Failed(single.error ?: "Export failed")
                }
            }
        }
    }

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
        if (pendingTreatment == null) editingEntry = null
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
                // the fingerprint finds the stored preview of this video (and goes into .cst files)
                fingerprint = withContext(Dispatchers.IO) {
                    runCatching {
                        Treatment.fingerprint(info.sizeBytes) { getApplication<Application>().contentResolver.openInputStream(info.uri)!! }
                    }.getOrNull()
                }
                fingerprint?.let { previews.touch(it) }
                loadThumbs()
                loadProxy(info)
                loadJoins(info)
                pendingTreatment?.let { applyTreatment(it) }
                pendingTreatment = null
                edit?.let { committed = it.trim to it.segments }
                seek(0)
            } catch (e: Exception) {
                clip = ClipState.Failed(e.message ?: e.toString())
            }
        }
    }

    private fun loadThumbs() {
        val src = source ?: return
        val fp = fingerprint
        thumbJob = viewModelScope.launch {
            fun show(frame: Int, bmp: Bitmap) {
                val t = Thumb(frame, bmp.asImageBitmap(), bmp)
                viewModelScope.launch {
                    val i = thumbs.indexOfFirst { it.frame > frame }.let { if (it < 0) thumbs.size else it }
                    thumbs.add(i, t)
                    if (!previewExact && preview == null) preview = bmp
                }
            }
            val stored = fp?.let { withContext(Dispatchers.IO) { previews.loadThumbs(it) } }
            if (stored != null) {
                for ((frame, jpeg) in stored) BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size)?.let { show(frame, it) }
                return@launch
            }
            val made = java.util.Collections.synchronizedList(mutableListOf<Pair<Int, ByteArray>>())
            src.thumbnails(max = 60, width = 192) { frame, bmp ->
                made += frame to java.io.ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.JPEG, 80, it) }.toByteArray()
                show(frame, bmp)
            }
            if (fp != null) withContext(Dispatchers.IO) { runCatching { previews.writeThumbs(fp, made.toList()) } }
        }
    }

    private fun loadJoins(info: ClipInfo) {
        joins = null
        joinsError = null
        smartOverride.clear()
        viewModelScope.launch {
            try {
                val fp = fingerprint
                joins = withContext(Dispatchers.IO) {
                    fp?.let { previews.loadJoins(it, info.frames.count) }
                        ?: Smart.joinPoints(getApplication(), info).also { j ->
                            if (fp != null) runCatching { previews.writeJoins(fp, info.frames.count, info.name, j) }
                        }
                }
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
                val t0 = System.nanoTime()
                val built = Proxy.build(getApplication(), info, previews, fingerprint) { p ->
                    proxy = p
                    viewModelScope.launch { proxyProgress = p.fraction }
                }
                android.util.Log.i("Vsc", "proxy of ${info.name} ready in ${(System.nanoTime() - t0) / 1_000_000} ms " +
                    "(${built.chunks.size} chunks)")
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.w("Vsc", "proxy failed", e)    // scrubbing falls back to thumbnails
            }
        }
    }

    /**
     * Deletes previews nobody needs (user rule, see [PreviewCache.cleanup]) – not before the app
     * has run 2 minutes, and only while nothing heavy runs (export, proxy build, keyframe
     * analysis); otherwise it tries again every 30 s.
     */
    private fun schedulePreviewCleanup() {
        viewModelScope.launch {
            delay(120_000)
            while (true) {
                val busy = ExportManager.hasWork || (clip is ClipState.Loaded && (proxyProgress < 1f || joins == null))
                if (!busy) break
                delay(30_000)
            }
            val app = getApplication<Application>()
            val n = withContext(Dispatchers.IO) {
                val inUse = ExportManager.batch.map { it.task.treatment.fingerprint }.toSet()
                previews.cleanup(fingerprint, inUse, CstStore(app).fingerprints())
            }
            android.util.Log.i("Vsc", "preview clean-up: $n removed, ${previews.totalBytes() / 1_000_000} MB kept")
        }
    }

    // ------------------------------------------------------------------ playhead

    /** Move the playhead: nearest thumbnail at once, the exact frame after 120 ms of rest. */
    fun seek(frame: Int) {
        stopPlayback()
        val e = edit ?: return
        val f = frame.coerceIn(0, e.info.frames.count - 1)
        playhead = f
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

    fun toStart() = seek(0)
    fun toEnd() { edit?.let { seek(it.info.frames.count - 1) } }

    /** Timeline tap: move there and select the section tapped (or none). */
    fun tapTimeline(frame: Int, radius: Int) {
        val e = edit ?: return
        val f = if (magnet) e.snap(frame, radius, pendingStart) else frame
        seek(f)
        selectedSection = e.sectionAt(f)
    }

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
                onFrame = { f -> playhead = f },
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

    /**
     * End a section at the playhead. Without a marked start it begins right after the section
     * before (or at the clip start; inside a section: that section's start) – see [ClipEdit.quickStart].
     */
    fun markEnd() {
        stopPlayback()
        val e = edit ?: return
        val start = pendingStart ?: e.quickStart(playhead)
        edit = e.addSection(start, playhead, sectionFps)
        pendingStart = null
        selectedSection = edit?.sectionAt(playhead) ?: -1
    }

    /** Select section [index] for editing (list tap); the playhead goes to its start. */
    fun selectSection(index: Int) {
        val s = edit?.segments?.getOrNull(index) ?: return
        seek(s.start)
        selectedSection = index
    }

    fun deselectSection() { selectedSection = -1 }

    /** The selected section now starts / ends at the playhead. */
    fun setSectionStartHere(index: Int) = changeRange(index) { s -> playhead to s.end - 1 }
    fun setSectionEndHere(index: Int) = changeRange(index) { s -> s.start to playhead }

    private fun changeRange(index: Int, range: (Segment) -> Pair<Int, Int>) {
        stopPlayback()
        val e = edit ?: return
        val s = e.segments.getOrNull(index) ?: return
        val (a, b) = range(s)
        edit = e.setSectionRange(index, a, b)
        selectedSection = edit?.segments?.indexOfFirst { it.start == minOf(a, b) } ?: -1
    }

    fun setSmooth(index: Int, atStart: Boolean, on: Boolean) {
        stopPlayback()
        edit = edit?.setSmooth(index, atStart, on)
    }

    /** The speed ramps (timeline): frames and the rates they go from / to. */
    fun rampZones(): List<RampZone> {
        val e = edit ?: return emptyList()
        val steps = Segments.rampSteps(usedSegments(e), 0, e.info.frames.count, e.info.realFps)
        val out = mutableListOf<RampZone>()
        for (st in steps) {
            val last = out.lastOrNull()
            if (last != null && last.end == st.start) out[out.lastIndex] = last.copy(end = st.end, to = st.fps)
            else out += RampZone(st.start, st.end, st.fps, st.fps)
        }
        return out
    }

    // ------------------------------------------------------------------ dragging a section border

    private var dragBase: ClipEdit? = null
    private var dragBorder = -1
    /** Border being dragged and where it is now (timeline highlight), or null. */
    var draggedBorder by mutableStateOf<Int?>(null)
        private set

    /** Start dragging the border at [border]; the neighbouring sections follow live. */
    fun beginBorderDrag(border: Int) {
        stopPlayback()
        dragBase = edit
        dragBorder = border
        draggedBorder = border
    }

    fun dragBorderTo(frame: Int) {
        val base = dragBase ?: return
        val (lo, hi) = base.borderRange(dragBorder)
        val q = frame.coerceIn(lo, hi)
        edit = base.previewSegments(base.movedBorder(dragBorder, q))
        draggedBorder = q
        seek(minOf(q, base.info.frames.count - 1))          // preview: the first frame after the border
    }

    fun endBorderDrag() {
        val base = dragBase ?: return
        val now = edit ?: return
        val q = draggedBorder ?: dragBorder
        edit = base.editSegments(now.segments, "Move border to frame ${q + 1}")
        dragBase = null
        draggedBorder = null
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

    /** Trim bracket dragged on the timeline to border [frame] (lossless / smart: keyframes). */
    fun dragTrim(isIn: Boolean, frame: Int) {
        stopPlayback()
        val e = edit ?: return
        if (isIn) {
            val f = frame.coerceIn(0, e.trimEnd - 1)
            edit = e.withIn(f, snap = snapsToKeyframes)
            edit?.let { seek(it.trim.start) }
        } else {
            val f = frame.coerceIn(e.trim.start + 1, e.info.frames.count)
            edit = e.withOut(f - 1, snap = snapsToKeyframes)
            edit?.let { seek(it.trimEnd - 1) }
        }
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

    // ------------------------------------------------------------------ export / batch / treatment

    private val treatmentMode: Treatment.Mode
        get() = when (mode) {
            Mode.LOSSLESS -> Treatment.Mode.LOSSLESS
            Mode.SMART -> Treatment.Mode.SMART
            Mode.REENCODE -> Treatment.Mode.REENCODE
        }

    /** The current clip, edit and settings as a treatment (what a .cst / batch entry holds). */
    private suspend fun snapshot(): Treatment.Data? {
        val e = edit ?: return null
        val info = e.info
        val fp = fingerprint ?: withContext(Dispatchers.IO) {
            Treatment.fingerprint(info.sizeBytes) { getApplication<Application>().contentResolver.openInputStream(info.uri)!! }
        }.also { fingerprint = it }
        val segs = if (mode == Mode.SMART) smartParts(e) else usedSegments(e)
        return Treatment.Data(info.name, info.sizeBytes, fp, info.frames.count,
            Treatment.Settings(treatmentMode, fps, usedSpeed, usedCodec, usedQuality, shortSide, sound, smartAuto,
                size = (job() as? ReencodeJob)?.outputSize()),
            e.trim, segs, info.uri.toString())
    }

    private fun blockers(): List<String> = when (val job = job()) {
        is LosslessJob -> job.blockers()
        is SmartJob -> if (joins == null) listOf("The keyframes of this clip are still being analysed") else job.blockers()
        is ReencodeJob -> job.blockers()
        else -> listOf("No clip")
    }

    private fun withTask(action: (ExportTask) -> Unit) {
        val e = edit ?: return
        val b = blockers()
        if (b.isNotEmpty()) {
            export = ExportState.Failed(b.joinToString("\n"))
            return
        }
        viewModelScope.launch {
            val t = snapshot() ?: return@launch
            action(ExportTask(ExportManager.newId(), e.info.uri, t, e.info.videoMime))
            committed = e.trim to e.segments
        }
    }

    /** Export now – runs in the export service (goes on in the background). */
    fun startExport() {
        stopPlayback()
        if (export is ExportState.Running) return
        withTask { ExportManager.exportNow(it) }
    }

    fun cancelExport() {
        ExportManager.entries.value.lastOrNull { !it.inBatch }?.let { ExportManager.cancel(it.task.id) }
    }

    fun addToBatch() = withTask {
        ExportManager.addToBatch(it)
        message = "Added to the batch list: ${it.treatment.sourceName} – ${it.label}"
    }

    fun updateBatchEntry() {
        val id = editingEntry ?: return
        withTask {
            ExportManager.updateBatchEntry(id, it)
            message = "Batch entry updated"
        }
    }

    fun exportBatch() = ExportManager.exportBatch()
    fun removeBatchEntry(id: Long) { ExportManager.remove(id); if (editingEntry == id) editingEntry = null }
    fun cancelBatchEntry(id: Long) = ExportManager.cancel(id)
    fun clearDoneEntries() = ExportManager.clearDone()
    fun cancelAll() = ExportManager.cancelAll()

    /** Load a batch entry into the editor (its clip with its treatment). */
    fun openEntry(entry: ExportManager.Entry) {
        val sameClip = (clip as? ClipState.Loaded)?.info?.uri == entry.task.uri
        if (sameClip) applyTreatment(entry.task.treatment) else {
            pendingTreatment = entry.task.treatment
            open(entry.task.uri)
        }
        editingEntry = entry.task.id
    }

    /** .cst text of the current clip (Save treatment / Share). */
    suspend fun treatmentText(): String? {
        val t = snapshot() ?: return null
        return Treatment.toJson(t, edit!!.info.videoMime)
    }

    /** "Save": straight into Documents/VideoSpeedControl/Clip Speed Treatments/ (no file dialog). */
    fun saveTreatment() {
        viewModelScope.launch {
            val text = treatmentText() ?: return@launch
            val name = treatmentFileName()
            message = try {
                withContext(Dispatchers.IO) { CstStore(getApplication()).save(name, text) }
                "Saved: ${CstStore.RELATIVE_PATH}$name"
            } catch (e: Exception) {
                "Could not save $name: ${e.message}"
            }
        }
    }

    fun treatmentFileName(): String = (edit?.info?.name?.substringBeforeLast('.') ?: "clip") + Treatment.SUFFIX

    /** Load a .cst onto the current clip – refused unless it was made for exactly this video. */
    fun loadTreatment(text: String, fileName: String) {
        viewModelScope.launch {
            try {
                val d = Treatment.fromJson(text, fileName)
                val e = edit ?: throw Treatment.TreatmentError("Open the clip first: ${d.sourceName}")
                val fp = fingerprint ?: withContext(Dispatchers.IO) {
                    Treatment.fingerprint(e.info.sizeBytes) { getApplication<Application>().contentResolver.openInputStream(e.info.uri)!! }
                }.also { fingerprint = it }
                d.check(e.info.name, e.info.sizeBytes, fp, e.info.frames.count)
                applyTreatment(d)
                message = "Treatment loaded: ${ExportTask.describe(d)}"
            } catch (ex: Treatment.TreatmentError) {
                message = ex.message
            }
        }
    }

    private fun applyTreatment(d: Treatment.Data) {
        val e = edit ?: return
        stopPlayback()
        val s = d.settings
        mode = when (s.mode) {
            Treatment.Mode.LOSSLESS -> Mode.LOSSLESS
            Treatment.Mode.SMART -> Mode.SMART
            Treatment.Mode.REENCODE -> Mode.REENCODE
        }
        prefs.edit().putString("mode", mode.name.lowercase()).apply()
        chooseFps(s.fps); chooseSpeed(s.speed); chooseCodec(s.codec); chooseQuality(s.quality); chooseShortSide(s.shortSide)
        sound = s.sound
        smartAuto = s.smartAuto
        // smart treatments list every part; the real-time ones are implicit in the editor
        val real = e.info.realFps
        val segs = if (s.mode == Treatment.Mode.SMART) d.segments.filter { it.fps != real } else d.segments
        edit = e.copy(trim = d.trim).editSegments(segs, "Load treatment")
        smartOverride.clear()
        if (s.mode == Treatment.Mode.SMART) {
            for (p in smartPieces()) {
                val flag = d.segments.any { it.reencode && it.start < p.end && it.end > p.start }
                if (flag != p.reencode) smartOverride[p.key] = flag
            }
        }
        selectedSection = -1
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
