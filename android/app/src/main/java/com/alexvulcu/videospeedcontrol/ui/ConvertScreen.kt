package com.alexvulcu.videospeedcontrol.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.alexvulcu.videospeedcontrol.core.ClipInfo
import com.alexvulcu.videospeedcontrol.core.Convert
import com.alexvulcu.videospeedcontrol.core.ConvertAudio
import com.alexvulcu.videospeedcontrol.core.OutMuxer
import com.alexvulcu.videospeedcontrol.core.Probe
import com.alexvulcu.videospeedcontrol.core.Quality
import com.alexvulcu.videospeedcontrol.core.Rational
import com.alexvulcu.videospeedcontrol.core.VideoCodec
import com.alexvulcu.videospeedcontrol.export.ExportManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import org.json.JSONObject

/**
 * The list of "Convert videos" (app-wide, so it survives leaving the screen). Files are read
 * (probed) two at a time; a converted file is an [ExportManager] entry ([Row.taskId]).
 * Pro mode (2026-11-04): a row can have its own settings ([Row.own]).
 */
object ConvertList {
    data class Row(val uri: Uri, val name: String, val info: ClipInfo? = null, val error: String? = null,
                   val taskId: Long? = null, val own: Convert.Settings? = null)

    val rows = MutableStateFlow<List<Row>>(emptyList())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val probing = Semaphore(2)

    /** Adds files (uri, display name); returns how many were new. */
    fun add(context: Context, files: List<Pair<Uri, String>>): Int {
        val known = rows.value.map { it.uri }.toSet()
        val new = files.distinctBy { it.first }.filter { it.first !in known }
        rows.update { it + new.map { (uri, name) -> Row(uri, name) } }
        val app = context.applicationContext
        for ((uri, _) in new) scope.launch {
            probing.withPermit {
                val result = runCatching { Probe.probe(app, uri) }
                rows.update { list ->
                    list.map { r ->
                        if (r.uri != uri) r
                        else result.fold({ r.copy(info = it, error = null) },
                            { r.copy(error = it.message ?: it.toString()) })
                    }
                }
            }
        }
        return new.size
    }

    fun remove(uri: Uri) = rows.update { list -> list.filterNot { it.uri == uri } }

    fun setOwn(uri: Uri, own: Convert.Settings?) = rows.update { list -> list.map { if (it.uri == uri) it.copy(own = own) else it } }

    /** Removes everything that is not waiting / being converted. */
    fun clear() {
        val busy = busyIds()
        val gone = rows.value.filter { it.taskId !in busy }
        ExportManager.clearConversions(gone.mapNotNull { it.taskId }.toSet())
        rows.update { list -> list.filter { it.taskId in busy } }
    }

    private fun busyIds(): Set<Long> = ExportManager.entries.value
        .filter { it.convert && (it.status == ExportManager.Status.WAITING || it.status == ExportManager.Status.RUNNING) }
        .map { it.task.id }.toSet()

    /** Rows that can be queued: readable, no conversion yet (or the last one failed / was cancelled). */
    fun todo(): List<Row> {
        val entries = ExportManager.entries.value.associateBy { it.task.id }
        return rows.value.filter { r ->
            r.info != null && (r.taskId == null || entries[r.taskId]?.status.let {
                it == null || it == ExportManager.Status.FAILED || it == ExportManager.Status.CANCELLED })
        }
    }

    /** Queues every row of [todo] with the settings [settingsFor] gives it. */
    fun start(settingsFor: (Row) -> Convert.Settings): Int {
        val tasks = todo().map { r -> r.uri to Convert.task(ExportManager.newId(), r.info!!, settingsFor(r)) }
        val ids = tasks.associate { (uri, t) -> uri to t.id }
        rows.update { list -> list.map { r -> ids[r.uri]?.let { r.copy(taskId = it) } ?: r } }
        ExportManager.convert(tasks.map { it.second })
        return tasks.size
    }
}

/** Stored choices: easy and pro general settings (JSON), the mode. */
private object ConvertPrefs {
    fun easy(p: android.content.SharedPreferences): Convert.Settings =
        p.getString("convert_easy", null)?.let { Convert.Settings.fromJson(runCatching { JSONObject(it) }.getOrNull()) }
            ?: Convert.Settings(   // 0.9.4 keys
                codec = runCatching { VideoCodec.valueOf(p.getString("convert_codec", "")!!) }.getOrNull()
                    ?.takeIf { it in Convert.CODECS } ?: Convert.CODECS.first(),
                quality = runCatching { Quality.valueOf(p.getString("convert_quality", "HIGH")!!) }.getOrDefault(Quality.HIGH),
                audio = if (p.getBoolean("convert_sound", true)) "default" else "none")

    fun general(p: android.content.SharedPreferences): Convert.Settings =
        p.getString("convert_general", null)?.let { Convert.Settings.fromJson(runCatching { JSONObject(it) }.getOrNull()) }
            ?: Convert.Settings(audio = "smart")
}

@Composable
fun ConvertScreen(onClose: () -> Unit, onStart: (() -> Unit) -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("vsc", Context.MODE_PRIVATE) }
    val rows by ConvertList.rows.collectAsState()
    val entries by ExportManager.entries.collectAsState()
    val byId = entries.associateBy { it.task.id }
    var pro by remember { mutableStateOf(prefs.getBoolean("convert_pro", false)) }
    var easy by remember { mutableStateOf(ConvertPrefs.easy(prefs)) }
    var general by remember { mutableStateOf(ConvertPrefs.general(prefs)) }
    var note by remember { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf<Uri?>(null) }

    fun settingsFor(r: ConvertList.Row) = if (!pro) easy else r.own ?: general

    fun take(uri: Uri) = runCatching {
        ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    val pickFiles = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        uris.forEach(::take)
        val files = uris.map { it to displayName(ctx, it) }
        val added = ConvertList.add(ctx, files)
        note = if (files.isEmpty()) null else trp("%d video added", "%d videos added", added, added)
    }
    val pickFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { tree ->
        if (tree != null) {
            take(tree)
            val files = videosInTree(ctx, tree)
            val added = ConvertList.add(ctx, files)
            note = if (files.isEmpty()) tr("No videos found in this folder.") else trp("%d video added", "%d videos added", added, added)
        }
    }

    val busy = rows.any { r -> r.taskId?.let { byId[it]?.status }.let { it == ExportManager.Status.WAITING || it == ExportManager.Status.RUNNING } }
    val reading = rows.count { it.info == null && it.error == null }
    val todoRows = rows.filter { r ->
        r.info != null && (r.taskId == null || byId[r.taskId]?.status.let {
            it == null || it == ExportManager.Status.FAILED || it == ExportManager.Status.CANCELLED })
    }
    val todo = todoRows.size
    val problems = todoRows.count { Convert.audioProblem(it.info!!, settingsFor(it)) != null }

    editing?.let { uri ->
        val r = rows.firstOrNull { it.uri == uri }
        if (r == null) editing = null
        else OwnSettingsDialog(r, r.own ?: general, onDone = { ConvertList.setOwn(uri, it); editing = null },
            onGeneral = { ConvertList.setOwn(uri, null); editing = null }, onDismiss = { editing = null })
    }

    Surface(Modifier.fillMaxSize().statusBarsPadding()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding().padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(tr("Convert videos"), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                OutlinedButton(onClose) { Text(tr("← Back")) }
            }
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                item {
                    Text(tr("Re-encodes many videos at once – for example old AVI files. The new files are saved in %s; " +
                        "the originals stay untouched.", Convert.FOLDER.trimEnd('/')), style = MaterialTheme.typography.bodySmall)
                }
                item {
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        listOf(false to tr("Easy"), true to tr("Pro")).forEachIndexed { i, (v, label) ->
                            SegmentedButton(selected = pro == v, enabled = !busy,
                                onClick = { pro = v; prefs.edit().putBoolean("convert_pro", v).apply() },
                                shape = SegmentedButtonDefaults.itemShape(i, 2)) { Text(label) }
                        }
                    }
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton({ pickFiles.launch(arrayOf("video/*")) }, enabled = !busy) { Text(tr("＋ Videos")) }
                        OutlinedButton({ pickFolder.launch(null) }, enabled = !busy) { Text(tr("＋ Folder")) }
                        if (rows.isNotEmpty()) TextButton({ ConvertList.clear(); note = null }, enabled = !busy) { Text(tr("Clear list")) }
                    }
                }
                note?.let { n -> item { Text(n, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary) } }
                items(rows, key = { it.uri.toString() }) { r ->
                    val e = r.taskId?.let { byId[it] }
                    val free = e == null || (e.status != ExportManager.Status.WAITING && e.status != ExportManager.Status.RUNNING)
                    ConvertRow(r, e, settingsFor(r), pro, enabled = free && !busy, onEdit = { editing = r.uri })
                    HorizontalDivider()
                }
                item {
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(if (pro) tr("General settings – for every video without own settings (⚙)") else tr("Settings for every video"),
                                style = MaterialTheme.typography.titleSmall)
                            if (pro) SettingsEditor(general, true, enabled = !busy) {
                                general = it; prefs.edit().putString("convert_general", it.toJson().toString()).apply()
                            } else SettingsEditor(easy, false, enabled = !busy) {
                                easy = it; prefs.edit().putString("convert_easy", it.toJson().toString()).apply()
                            }
                        }
                    }
                }
            }
            val summary = buildList {
                add(trp("%d video to convert", "%d videos to convert", todo, todo))
                if (reading > 0) add(trp("%d still being read", "%d still being read", reading, reading))
                rows.count { it.error != null }.takeIf { it > 0 }?.let { add(trp("%d can't be read", "%d can't be read", it, it)) }
                if (problems > 0) add(trp("%d with settings that don't fit (⚠)", "%d with settings that don't fit (⚠)", problems, problems))
            }.joinToString(" · ")
            Text(summary, style = MaterialTheme.typography.bodySmall)
            Row(Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (busy) {
                    OutlinedButton({
                        rows.mapNotNull { it.taskId }.forEach { id ->
                            val s = byId[id]?.status
                            if (s == ExportManager.Status.WAITING || s == ExportManager.Status.RUNNING) ExportManager.cancel(id)
                        }
                    }, Modifier.weight(1f)) { Text(tr("Cancel")) }
                } else {
                    TextButton({ openFolder(ctx, Convert.FOLDER) }) { Text(tr("📁 Open folder")) }
                    Button({ onStart { ConvertList.start(::settingsFor) } }, Modifier.weight(1f),
                        enabled = todo > 0 && reading == 0 && problems == 0) {
                        Text(if (todo > 0) trp("Convert %d video", "Convert %d videos", todo, todo) else tr("Convert"))
                    }
                }
            }
        }
    }
}

/** Short description of a row's settings (desktop: convert.describe). */
fun describe(s: Convert.Settings): String = buildList {
    add("${Convert.codecLabel(s.codec)} ${s.container.name}")
    s.fps?.let { add("${fmtFps(it.toDouble())} fps") }
    add(when (s.rate) {
        Convert.Rate.LEVEL -> tr(s.quality.label)
        Convert.Rate.KBPS -> "${s.kbps} kbit/s"
        Convert.Rate.SMART -> if (s.goal == Convert.Goal.IDENTICAL) tr("smart, looks identical") else tr("smart, smaller")
    })
    add(when (s.audio) {
        "default" -> "AAC"
        "smart" -> tr("sound smart")
        "copy" -> tr("sound copied")
        "none" -> tr("no sound")
        else -> buildString {
            append(audioLabel(s.audio))
            s.channels?.let { append(" "); append(channelLabel(it)) }
            if (s.audioKbps != null && s.audio != "flac") append(" ${s.audioKbps}k")
        }
    })
}.joinToString(" · ")

private fun audioLabel(mode: String) = when (mode) {
    "aac" -> "AAC"; "opus" -> "Opus"; "flac" -> tr("FLAC (lossless)"); "copy" -> tr("Copy unchanged")
    "smart" -> tr("Smart"); "none" -> tr("No sound"); else -> mode
}

private fun channelLabel(ch: Int?) = when (ch) {
    null -> tr("Like the original"); 1 -> tr("Mono"); 2 -> tr("Stereo"); 6 -> "5.1"; else -> "$ch"
}

/** What the smart rules expect for this video, e.g. "Smart: ≈ 230 kbit/s · sound copied · ≈ 45 %". */
private fun smartText(info: ClipInfo, s: Convert.Settings): String? {
    if (!s.usesRules) return null
    val plan = runCatching { Convert.plan(info, s) }.getOrNull() ?: return null
    val sug = plan.suggestion ?: return null
    val video = if (s.rate == Convert.Rate.SMART) "≈ ${sug.videoKbps} kbit/s" else null
    val sound = if (s.audio == "smart") when (sug.audio) {
        "copy" -> tr("sound copied"); "none" -> tr("no sound"); else -> "AAC ${sug.audioKbps} kbit/s"
    } else null
    val share = if (info.sizeBytes > 0 && s.rate == Convert.Rate.SMART)
        tr("≈ %d %% of the original", (sug.sizeBytes * 100 / info.sizeBytes).toInt()) else null
    return tr("Smart: %s", listOfNotNull(video, sound, share).joinToString(" · ")) + if (sug.note.isNotEmpty()) " – ${sug.note}" else ""
}

@Composable
private fun ConvertRow(r: ConvertList.Row, e: ExportManager.Entry?, s: Convert.Settings, pro: Boolean, enabled: Boolean,
                       onEdit: () -> Unit) {
    val ctx = LocalContext.current
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Column(Modifier.weight(1f)) {
            Text(r.name, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val info = r.info
            val detail = when {
                r.error != null -> tr("Can't be read: %s", r.error)
                info == null -> tr("Reading …")
                else -> "${info.codecName} ${info.width}×${info.height}, ${LosslessJobFmt.fps(info)} fps, " +
                    formatDuration(info.durationUs) + (info.audioMime?.let { " · ${Convert.audioName(it)}" } ?: "")
            }
            when (e?.status) {
                ExportManager.Status.RUNNING -> {
                    Text(tr("Converting … %d %%", (e.progress * 100).toInt()), style = MaterialTheme.typography.bodySmall)
                    LinearProgressIndicator(progress = { e.progress }, modifier = Modifier.fillMaxWidth())
                }
                ExportManager.Status.WAITING -> Text(tr("waiting"), style = MaterialTheme.typography.bodySmall)
                ExportManager.Status.DONE -> Text("✔ " + (e.output ?: ""), style = MaterialTheme.typography.bodySmall,
                    color = PlayGreen)
                ExportManager.Status.FAILED -> Text(tr("Failed: %s", e.error), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error)
                ExportManager.Status.CANCELLED -> Text(tr("Cancelled"), style = MaterialTheme.typography.bodySmall)
                else -> {
                    Text(detail, style = MaterialTheme.typography.bodySmall,
                        color = if (r.error != null) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
                    if (info != null) {
                        if (pro) Text(if (r.own != null) tr("Own: %s", describe(r.own)) else tr("General settings"),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                        Convert.audioProblem(info, s)?.let {
                            Text("⚠ $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                        }
                        remember(info, s) { smartText(info, s) }?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
        if (e?.status == ExportManager.Status.DONE && e.outputUri != null) {
            IconButton({
                ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(e.outputUri, "video/*")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
            }) { Icon(PlayIcon, tr("Play %s", e.output), Modifier.size(28.dp), tint = PlayGreen) }
        }
        if (pro && enabled && r.info != null) TextButton(onEdit) { Text("⚙") }
        if (enabled) TextButton({ ConvertList.remove(r.uri) }) { Text("✕") }
    }
}

@Composable
private fun OwnSettingsDialog(r: ConvertList.Row, start: Convert.Settings, onDone: (Convert.Settings) -> Unit,
                              onGeneral: () -> Unit, onDismiss: () -> Unit) {
    var s by remember { mutableStateOf(start) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(tr("Own settings"), style = MaterialTheme.typography.titleMedium) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(r.name, style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                SettingsEditor(s, true, info = r.info) { s = it }
                r.info?.let { info ->
                    Convert.audioProblem(info, s)?.let { Text("⚠ $it", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    smartText(info, s)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
        },
        confirmButton = { TextButton({ onDone(s) }) { Text(tr("Done")) } },
        dismissButton = { if (r.own != null) TextButton(onGeneral) { Text(tr("Use general settings")) } else TextButton(onDismiss) { Text(tr("Cancel")) } },
    )
}

/**
 * The settings form. Easy: codec, quality level, Smart (+ goal), sound. Pro: frame rate,
 * container, codec, picture (level / kbit/s / smart), sound codec, channels, sound kbit/s;
 * combinations a container can't hold are disabled. [info] (one video) names its own frame rate.
 */
@Composable
private fun SettingsEditor(s: Convert.Settings, pro: Boolean, enabled: Boolean = true, info: ClipInfo? = null,
                           onChange: (Convert.Settings) -> Unit) {
    @Composable
    fun <T> Segments(label: String?, options: List<Pair<T, String>>, value: T, isEnabled: (T) -> Boolean = { true },
                     choose: (T) -> Unit) {
        if (label != null) Text(label, style = MaterialTheme.typography.labelLarge)
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            options.forEachIndexed { i, (v, text) ->
                SegmentedButton(selected = value == v, enabled = enabled && isEnabled(v), onClick = { choose(v) },
                    shape = SegmentedButtonDefaults.itemShape(i, options.size)) { Text(text, maxLines = 1) }
            }
        }
    }
    val codecs = Convert.CODECS.map { it to Convert.codecLabel(it) }
    val levels = listOf(Quality.GOOD, Quality.HIGH, Quality.VERY_HIGH).map { it to tr(it.label) }
    val goals = listOf(Convert.Goal.IDENTICAL to tr("Looks identical"), Convert.Goal.SMALLER to tr("Smaller"))

    if (!pro) {
        Segments(tr("Codec"), codecs, s.codec) { onChange(s.copy(codec = it)) }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(tr("Smart: smallest file that keeps picture and sound"))
                Text(tr("The data rate is chosen per video from its codec and data rate."),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Switch(s.rate == Convert.Rate.SMART, { on ->
                onChange(s.copy(rate = if (on) Convert.Rate.SMART else Convert.Rate.LEVEL,
                    audio = if (s.audio == "none") "none" else if (on) "smart" else "default"))
            }, enabled = enabled)
        }
        if (s.rate == Convert.Rate.SMART) Segments(tr("Goal"), goals, s.goal) { onChange(s.copy(goal = it)) }
        else Segments(tr("Quality"), levels, s.quality) { onChange(s.copy(quality = it)) }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(tr("Keep the sound"), modifier = Modifier.weight(1f))
            Switch(s.audio != "none", { on ->
                onChange(s.copy(audio = if (!on) "none" else if (s.rate == Convert.Rate.SMART) "smart" else "default"))
            }, enabled = enabled)
        }
        return
    }

    // ---- pro
    val fpsOptions: List<Rational?> = listOf(null) + FPS_CHOICES
    ChoiceDropdown(tr("Frame rate"), s.fps, fpsOptions, enabled, { r ->
        if (r == null) (info?.let { tr("%s fps (original)", fmtFps(it.fps.toDouble())) } ?: tr("Original (each video's own)"))
        else "${fmtFps(r.toDouble())} fps"
    }) { onChange(s.copy(fps = it)) }
    Segments(tr("Container"), OutMuxer.Container.entries.map { it to it.name }, s.container,
        isEnabled = { OutMuxer.canHoldVideo(it, s.codec) }) { c ->
        onChange(s.copy(container = c, audio = if (s.audio in ConvertAudio.MIMES && !OutMuxer.canHold(c, ConvertAudio.MIMES[s.audio])) "aac" else s.audio))
    }
    if (s.container == OutMuxer.Container.MOV) Text(tr("MOV: saved as an MP4-type file with the .mov name (plays on Apple devices)."),
        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    Segments(tr("Codec"), codecs, s.codec) { c ->
        onChange(s.copy(codec = c, container = if (OutMuxer.canHoldVideo(s.container, c)) s.container else OutMuxer.Container.MP4))
    }
    Segments(tr("Picture"), listOf(Convert.Rate.LEVEL to tr("Quality"), Convert.Rate.KBPS to "kbit/s", Convert.Rate.SMART to tr("Smart")),
        s.rate) { onChange(s.copy(rate = it)) }
    when (s.rate) {
        Convert.Rate.LEVEL -> Segments(null, levels, s.quality) { onChange(s.copy(quality = it)) }
        Convert.Rate.KBPS -> NumberField(tr("Data rate (kbit/s)"), s.kbps, enabled) { onChange(s.copy(kbps = it.coerceIn(20, 200_000))) }
        Convert.Rate.SMART -> Segments(tr("Goal"), goals, s.goal) { onChange(s.copy(goal = it)) }
    }
    val audioModes = listOf("smart", "copy", "aac", "opus", "flac", "none")
    ChoiceDropdown(tr("Sound"), s.audio.takeIf { it != "default" } ?: "aac", audioModes, enabled, ::audioLabel,
        isEnabled = { m -> ConvertAudio.MIMES[m]?.let { OutMuxer.canHold(s.container, it) } ?: true }) { onChange(s.copy(audio = it)) }
    if (s.audio == "smart" && s.rate != Convert.Rate.SMART) Segments(tr("Goal"), goals, s.goal) { onChange(s.copy(goal = it)) }
    if (s.audio in ConvertAudio.MIMES) {
        val max = ConvertAudio.MAX_CHANNELS.getValue(s.audio)
        Segments(tr("Channels"), listOf<Int?>(null, 1, 2, 6).filter { it == null || it <= max }.map { it to channelLabel(it) },
            s.channels) { onChange(s.copy(channels = it)) }
        Text(tr("Never more channels than the original has."), style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (s.audio != "flac") NumberField(tr("Sound data rate (kbit/s, empty = default)"), s.audioKbps, enabled, allowEmpty = true) {
            onChange(s.copy(audioKbps = it.takeIf { v -> v > 0 }?.coerceIn(8, 512)))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> ChoiceDropdown(label: String, value: T, choices: List<T>, enabled: Boolean, text: (T) -> String,
                               isEnabled: (T) -> Boolean = { true }, onChoose: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { if (enabled) open = it }) {
        OutlinedTextField(
            value = text(value), onValueChange = {}, readOnly = true, enabled = enabled, singleLine = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
            modifier = Modifier.fillMaxWidth().menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for (c in choices) DropdownMenuItem(text = { Text(text(c)) }, enabled = isEnabled(c), onClick = { onChoose(c); open = false })
        }
    }
}

@Composable
private fun NumberField(label: String, value: Int?, enabled: Boolean, allowEmpty: Boolean = false, onValue: (Int) -> Unit) {
    var text by remember(value) { mutableStateOf(value?.toString() ?: "") }
    OutlinedTextField(text, { t ->
        val digits = t.filter(Char::isDigit).take(6)
        text = digits
        digits.toIntOrNull()?.let(onValue) ?: if (allowEmpty && digits.isEmpty()) onValue(0) else Unit
    }, label = { Text(label) }, singleLine = true, enabled = enabled,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
}

private object LosslessJobFmt {
    fun fps(info: ClipInfo) = com.alexvulcu.videospeedcontrol.core.LosslessJob.pyG(info.fps.toDouble(), 4)
}

private fun formatDuration(us: Long): String {
    val s = (us / 1_000_000).toInt()
    return if (s >= 3600) "%d:%02d:%02d".format(s / 3600, s / 60 % 60, s % 60) else "%d:%02d".format(s / 60, s % 60)
}

private fun displayName(ctx: Context, uri: Uri): String =
    ctx.contentResolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)
        ?.use { c -> if (c.moveToFirst()) c.getString(0) else null } ?: (uri.lastPathSegment ?: "video")

/** Videos in a folder chosen with the system picker, sub-folders included, in natural order per folder. */
private fun videosInTree(ctx: Context, tree: Uri): List<Pair<Uri, String>> {
    val out = ArrayList<Pair<Uri, String>>()
    fun walk(docId: String, depth: Int) {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
        val files = ArrayList<Triple<String, String, String>>()   // id, name, mime
        ctx.contentResolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE), null, null, null)
            ?.use { c -> while (c.moveToNext()) files += Triple(c.getString(0), c.getString(1) ?: "", c.getString(2) ?: "") }
        val sorted = files.filterNot { it.second.startsWith(".") }.sortedWith(compareBy(Convert.naturalOrder) { it.second })
        for ((id, name, mime) in sorted) {
            if (mime == DocumentsContract.Document.MIME_TYPE_DIR) continue
            if (mime.startsWith("video/") || Convert.isVideoName(name))
                out += DocumentsContract.buildDocumentUriUsingTree(tree, id) to name
        }
        if (depth < 8) for ((id, _, mime) in sorted) if (mime == DocumentsContract.Document.MIME_TYPE_DIR) walk(id, depth + 1)
    }
    walk(DocumentsContract.getTreeDocumentId(tree), 0)
    return out
}
