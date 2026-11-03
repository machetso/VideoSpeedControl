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
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.alexvulcu.videospeedcontrol.core.ClipInfo
import com.alexvulcu.videospeedcontrol.core.Convert
import com.alexvulcu.videospeedcontrol.core.Probe
import com.alexvulcu.videospeedcontrol.core.Quality
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

/**
 * The list of "Convert videos" (app-wide, so it survives leaving the screen). Files are read
 * (probed) two at a time; a converted file is an [ExportManager] entry ([Row.taskId]).
 */
object ConvertList {
    data class Row(val uri: Uri, val name: String, val info: ClipInfo? = null, val error: String? = null,
                   val taskId: Long? = null)

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

    /** Queues every readable row that has no conversion yet (or whose last one failed / was cancelled). */
    fun start(codec: VideoCodec, quality: Quality, sound: Boolean): Int {
        val entries = ExportManager.entries.value.associateBy { it.task.id }
        val todo = rows.value.filter { r ->
            r.info != null && (r.taskId == null || entries[r.taskId]?.status.let {
                it == null || it == ExportManager.Status.FAILED || it == ExportManager.Status.CANCELLED })
        }
        val tasks = todo.map { r -> r.uri to Convert.task(ExportManager.newId(), r.info!!, codec, quality, sound) }
        val ids = tasks.associate { (uri, t) -> uri to t.id }
        rows.update { list -> list.map { r -> ids[r.uri]?.let { r.copy(taskId = it) } ?: r } }
        ExportManager.convert(tasks.map { it.second })
        return tasks.size
    }
}

@Composable
fun ConvertScreen(onClose: () -> Unit, onStart: (() -> Unit) -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("vsc", Context.MODE_PRIVATE) }
    val rows by ConvertList.rows.collectAsState()
    val entries by ExportManager.entries.collectAsState()
    val byId = entries.associateBy { it.task.id }
    var codec by remember {
        mutableStateOf(runCatching { VideoCodec.valueOf(prefs.getString("convert_codec", "")!!) }.getOrNull()
            ?.takeIf { it in Convert.CODECS } ?: Convert.CODECS.first())
    }
    var quality by remember {
        mutableStateOf(runCatching { Quality.valueOf(prefs.getString("convert_quality", "HIGH")!!) }.getOrDefault(Quality.HIGH))
    }
    var sound by remember { mutableStateOf(prefs.getBoolean("convert_sound", true)) }
    var note by remember { mutableStateOf<String?>(null) }

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
    val todo = rows.count { r ->
        r.info != null && (r.taskId == null || byId[r.taskId]?.status.let {
            it == null || it == ExportManager.Status.FAILED || it == ExportManager.Status.CANCELLED })
    }

    Surface(Modifier.fillMaxSize().statusBarsPadding()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding().padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(tr("Convert videos"), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                OutlinedButton(onClose) { Text(tr("← Back")) }
            }
            Text(tr("Re-encodes many videos with the same settings – for example old AVI files. Length, frame rate, " +
                "picture size and sound stay as they are. The new files are saved as MP4 in %s; the originals stay untouched.",
                Convert.FOLDER.trimEnd('/')), style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton({ pickFiles.launch(arrayOf("video/*")) }, enabled = !busy) { Text(tr("＋ Videos")) }
                OutlinedButton({ pickFolder.launch(null) }, enabled = !busy) { Text(tr("＋ Folder")) }
                if (rows.isNotEmpty()) TextButton({ ConvertList.clear(); note = null }, enabled = !busy) { Text(tr("Clear list")) }
            }
            note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary) }

            LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
                items(rows, key = { it.uri.toString() }) { r ->
                    val e = r.taskId?.let { byId[it] }
                    ConvertRow(r, e, enabled = e == null || (e.status != ExportManager.Status.WAITING && e.status != ExportManager.Status.RUNNING))
                    HorizontalDivider()
                }
            }

            Text(tr("Codec"), style = MaterialTheme.typography.labelLarge)
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                Convert.CODECS.forEachIndexed { i, c ->
                    SegmentedButton(selected = codec == c, enabled = !busy,
                        onClick = { codec = c; prefs.edit().putString("convert_codec", c.name).apply() },
                        shape = SegmentedButtonDefaults.itemShape(i, Convert.CODECS.size)) { Text(Convert.codecLabel(c)) }
                }
            }
            Text(tr("Quality"), style = MaterialTheme.typography.labelLarge)
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                val levels = listOf(Quality.GOOD, Quality.HIGH, Quality.VERY_HIGH)
                levels.forEachIndexed { i, q ->
                    SegmentedButton(selected = quality == q, enabled = !busy,
                        onClick = { quality = q; prefs.edit().putString("convert_quality", q.name).apply() },
                        shape = SegmentedButtonDefaults.itemShape(i, levels.size)) { Text(tr(q.label)) }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(tr("Keep the sound"), modifier = Modifier.weight(1f))
                Switch(sound, { sound = it; prefs.edit().putBoolean("convert_sound", it).apply() }, enabled = !busy)
            }
            val summary = buildList {
                add(trp("%d video to convert", "%d videos to convert", todo, todo))
                if (reading > 0) add(trp("%d still being read", "%d still being read", reading, reading))
                rows.count { it.error != null }.takeIf { it > 0 }?.let { add(trp("%d can't be read", "%d can't be read", it, it)) }
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
                    Button({ onStart { ConvertList.start(codec, quality, sound) } }, Modifier.weight(1f),
                        enabled = todo > 0 && reading == 0) {
                        Text(if (todo > 0) trp("Convert %d video", "Convert %d videos", todo, todo) else tr("Convert"))
                    }
                }
            }
        }
    }
}

@Composable
private fun ConvertRow(r: ConvertList.Row, e: ExportManager.Entry?, enabled: Boolean) {
    val ctx = LocalContext.current
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.weight(1f)) {
            Text(r.name, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val info = r.info
            val detail = when {
                r.error != null -> tr("Can't be read: %s", r.error)
                info == null -> tr("Reading …")
                else -> "${info.codecName} ${info.width}×${info.height}, ${LosslessJobFmt.fps(info)} fps, " +
                    formatDuration(info.durationUs)
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
                else -> Text(detail, style = MaterialTheme.typography.bodySmall,
                    color = if (r.error != null) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (e?.status == ExportManager.Status.DONE && e.outputUri != null) {
            IconButton({
                ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(e.outputUri, "video/*")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
            }) { Icon(PlayIcon, tr("Play %s", e.output), Modifier.size(28.dp), tint = PlayGreen) }
        }
        if (enabled) TextButton({ ConvertList.remove(r.uri) }) { Text("✕") }
    }
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
