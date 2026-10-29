package com.alexvulcu.videospeedcontrol.ui

import android.content.Intent
import android.text.format.Formatter
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.ui.compose.PlayerSurface
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.material3.FilterChip
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import com.alexvulcu.videospeedcontrol.core.ClipEdit
import com.alexvulcu.videospeedcontrol.core.ClipInfo
import com.alexvulcu.videospeedcontrol.core.Rational
import com.alexvulcu.videospeedcontrol.core.Segments
import com.alexvulcu.videospeedcontrol.core.LosslessJob
import com.alexvulcu.videospeedcontrol.core.Quality
import com.alexvulcu.videospeedcontrol.core.ReencodeJob
import com.alexvulcu.videospeedcontrol.core.SmartJob
import com.alexvulcu.videospeedcontrol.export.ExportManager
import androidx.compose.material3.Checkbox
import com.alexvulcu.videospeedcontrol.core.VideoCodec
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

@Composable
fun PreviewPane(vm: EditorViewModel, info: ClipInfo) {
    val aspect = info.displayWidth.toFloat() / maxOf(1, info.displayHeight)
    val stepPx = with(LocalDensity.current) { 8.dp.toPx() }
    var jog by remember { mutableStateOf(0f) }
    Box(
        Modifier.fillMaxWidth().heightIn(max = 420.dp).aspectRatio(aspect.coerceAtLeast(0.5f))
            .background(Color.Black)
            // jog: drag sideways on the picture = one frame per 8 dp (finer than the timeline)
            .pointerInput(info.uri) {
                detectHorizontalDragGestures(onDragStart = { jog = 0f }) { change, dx ->
                    change.consume()
                    jog += dx
                    val steps = (jog / stepPx).toInt()
                    if (steps != 0) {
                        jog -= steps * stepPx
                        vm.step(steps)
                    }
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        if (vm.playingVideo) {
            PlayerSurface(vm.previewPlayer.player, Modifier.fillMaxSize())
        } else vm.preview?.let {
            Image(it.asImageBitmap(), contentDescription = "Frame ${vm.playhead + 1}",
                modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
        }
    }
}

@Composable
fun TransportPanel(vm: EditorViewModel, edit: ClipEdit) {
    val fm = edit.info.frames
    val p = vm.playhead
    val job = vm.job() ?: return
    val inRange = p >= edit.trim.start && p < edit.trimEnd
    val outT = if (inRange) secs(Segments.outputTime(job.pieces(), p).toDouble()) else "cut"
    val key = if (p in fm.keyframes) " · keyframe" else ""
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Frame ${p + 1} / ${fm.count}$key · source ${secs((fm.ptsUs[p] - fm.ptsUs[0]) / 1e6)} · output $outT",
            style = MaterialTheme.typography.bodySmall)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Button(vm::togglePlay) { Text(if (vm.playing) "■ Stop" else "▶ Play preview") }
            Text(
                "  ${clock(job.outputDuration.toDouble())} · ${speedWords(job.speed.toDouble())}" +
                    if (job.hasSegments) " on average" else "",
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f),
            )
            FilterChip(selected = vm.magnet, onClick = vm::toggleMagnet, label = { Text("🧲") })
        }
        Text(
            if (vm.proxyProgress < 1f) "Preparing frames for exact scrubbing… ${(vm.proxyProgress * 100).toInt()} %"
            else "Drag on the picture to move frame by frame.",
            style = MaterialTheme.typography.bodySmall,
        )
        // start of clip · previous keyframe · one frame back / ahead · next keyframe · end of clip
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            val pad = PaddingValues(horizontal = 6.dp)
            FilledTonalButton(vm::toStart, contentPadding = pad) { Icon(FirstIcon, "first frame", Modifier.size(22.dp)) }
            FilledTonalButton(vm::previousKeyframe, contentPadding = pad) {
                Icon(KeyMinusIcon, "previous keyframe", Modifier.size(width = 30.dp, height = 26.dp))
            }
            FilledTonalButton({ vm.step(-1) }, contentPadding = pad) { Text("◀ 1") }
            FilledTonalButton({ vm.step(1) }, contentPadding = pad) { Text("1 ▶") }
            FilledTonalButton(vm::nextKeyframe, contentPadding = pad) {
                Icon(KeyPlusIcon, "next keyframe", Modifier.size(width = 30.dp, height = 26.dp))
            }
            FilledTonalButton(vm::toEnd, contentPadding = pad) { Icon(LastIcon, "last frame", Modifier.size(22.dp)) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RateDropdown(
    label: String,
    value: Rational,
    choices: List<Rational>,
    text: (Rational) -> String,
    onChoose: (Rational) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { if (enabled) open = it }, modifier = modifier) {
        OutlinedTextField(
            value = text(value), onValueChange = {}, readOnly = true, enabled = enabled, singleLine = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
            modifier = Modifier.fillMaxWidth().menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for (r in choices) DropdownMenuItem(text = { Text(text(r)) }, onClick = { onChoose(r); open = false })
        }
    }
}

@Composable
fun SectionsPanel(vm: EditorViewModel, edit: ClipEdit) {
    val real = edit.info.realFps
    val rates = sectionRates(real)
    var confirmClear by remember { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Speed sections", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                TextButton(vm::undo, enabled = edit.undo.isNotEmpty()) {
                    Text(if (edit.undo.isEmpty()) "↶ Undo" else "↶ Undo (${edit.undo.size})")
                }
                TextButton(vm::redo, enabled = edit.redo.isNotEmpty()) {
                    Text(if (edit.redo.isEmpty()) "↷ Redo" else "↷ Redo (${edit.redo.size})")
                }
            }
            edit.undo.lastOrNull()?.let {
                Text("Last change: ${it.what}", style = MaterialTheme.typography.bodySmall,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            edit.segments.getOrNull(vm.selectedSection)?.let { SectionEditor(vm, edit, vm.selectedSection, rates) }
            RateDropdown("New sections play at", vm.sectionFps, rates, { sectionFpsLabel(real, it) },
                vm::chooseSectionFps)
            val start = vm.pendingStart
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Button(vm::markStart) { Text("[ Start") }
                Button(vm::markEnd) { Text("End ]") }
                if (start != null) {
                    TextButton(vm::cancelMark) { Text("Cancel") }
                }
            }
            val from = start ?: edit.quickStart(vm.playhead)
            Text(
                if (start == null) "“End” makes a section from frame ${from + 1} to the playhead (right after the " +
                    "section before it, or from the start). For another start, tap “Start” first."
                else "Start at frame ${start + 1} – now move to the last frame and tap “End”.",
                style = MaterialTheme.typography.bodySmall,
            )
            if (edit.segments.isNotEmpty()) {
                HorizontalDivider()
                Text("Tap a section (here or on the timeline) to edit it; drag a border on the timeline to " +
                    "move it.", style = MaterialTheme.typography.bodySmall)
            }
            edit.segments.forEachIndexed { i, s ->
                val len = (Rational.of((s.end - s.start).toLong()) / s.fps).toDouble()
                val bg = if (i == vm.selectedSection) MaterialTheme.colorScheme.secondaryContainer else Color.Transparent
                Row(Modifier.fillMaxWidth().background(bg).clickable { vm.selectSection(i) }.padding(6.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Frames ${s.start + 1}–${s.end} · plays ${secs(len)}", style = MaterialTheme.typography.bodyMedium)
                        Text(sectionFpsLabel(real, s.fps) + smoothNote(s), style = MaterialTheme.typography.bodySmall)
                    }
                    Text("Edit ›", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                }
            }
            if (edit.segments.isNotEmpty()) {
                TextButton({ confirmClear = true }) { Text("Clear sections") }
            }
        }
    }
    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text("Clear all sections?") },
            text = { Text("All ${edit.segments.size} speed sections of this clip are removed. You can undo this.") },
            confirmButton = { TextButton({ vm.clearSections(); confirmClear = false }) { Text("Clear") } },
            dismissButton = { TextButton({ confirmClear = false }) { Text("Keep") } },
        )
    }
}

private fun smoothNote(s: com.alexvulcu.videospeedcontrol.core.Segment): String = when {
    s.smoothStart && s.smoothEnd -> " · smooth in and out"
    s.smoothStart -> " · smooth in"
    s.smoothEnd -> " · smooth out"
    else -> ""
}

/** Editing the selected section: rate, start / end at the playhead, smooth transitions, remove. */
@Composable
private fun SectionEditor(vm: EditorViewModel, edit: ClipEdit, index: Int, rates: List<Rational>) {
    val s = edit.segments[index]
    val real = edit.info.realFps
    Card(colors = androidx.compose.material3.CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val len = (Rational.of((s.end - s.start).toLong()) / s.fps).toDouble()
                Text("Section ${index + 1}: frames ${s.start + 1}–${s.end} · plays ${secs(len)}",
                    style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                TextButton(vm::deselectSection) { Text("Done") }
            }
            RateDropdown("Frame rate", s.fps, rates, { sectionFpsLabel(real, it) }, { vm.setSectionFps(index, it) })
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton({ vm.setSectionStartHere(index) }) { Text("Start = playhead") }
                OutlinedButton({ vm.setSectionEndHere(index) }) { Text("End = playhead") }
            }
            for (atStart in listOf(true, false)) {
                val other = edit.neighbourRate(index, atStart)
                val on = if (atStart) s.smoothStart else s.smoothEnd
                val possible = other != null && other != s.fps
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (atStart) "Smooth transition in" else "Smooth transition out",
                            style = MaterialTheme.typography.bodyMedium)
                        Text(
                            when {
                                other == null -> if (atStart) "Starts with the clip" else "Ends with the clip"
                                !possible -> "Same speed on the other side"
                                else -> {
                                    val a = speedWords((if (atStart) other / real else s.fps / real).toDouble())
                                    val b = speedWords((if (atStart) s.fps / real else other / real).toDouble())
                                    "$a → $b, changing evenly over 0.5 s"
                                }
                            },
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Switch(on, { vm.setSmooth(index, atStart, it) }, enabled = possible || on)
                }
            }
            TextButton({ vm.removeSection(index) }) { Text("Remove section", color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
fun TrimPanel(vm: EditorViewModel, edit: ClipEdit) {
    val count = edit.info.frames.count
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Trim", style = MaterialTheme.typography.titleMedium)
            Text(
                if (edit.trim.start == 0 && edit.trim.end == null) "Whole clip (frames 1–$count)"
                else "Frames ${edit.trim.start + 1}–${edit.trimEnd} of $count",
                style = MaterialTheme.typography.bodyMedium,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(vm::setIn) { Text("Set in") }
                OutlinedButton(vm::setOut) { Text("Set out") }
                TextButton(vm::clearTrim, enabled = edit.trim.start != 0 || edit.trim.end != null) { Text("Reset") }
            }
            Text(
                if (vm.snapsToKeyframes)
                    "Lossless and smart export can only cut at keyframes (the ticks under the timeline): only they are " +
                        "complete pictures, all other frames store differences to their neighbours. In and out " +
                        "snap to the nearest keyframe."
                else "Re-encoding cuts at any frame.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
fun ExportCard(vm: EditorViewModel, edit: ClipEdit, onExport: () -> Unit = vm::startExport) {
    val ctx = LocalContext.current
    val info = edit.info
    val job = vm.job() ?: return
    val lossless = vm.mode == EditorViewModel.Mode.LOSSLESS
    val fpsChoices = if (lossless) (FPS_CHOICES + info.realFps).distinct().sorted() else FPS_CHOICES
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Export", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                // Easy hides the codec details (codec, quality); Pro shows everything
                SingleChoiceSegmentedButtonRow {
                    listOf(true to "Easy", false to "Pro").forEachIndexed { i, (easy, label) ->
                        SegmentedButton(selected = vm.easy == easy, onClick = { vm.chooseEasy(easy) },
                            shape = SegmentedButtonDefaults.itemShape(i, 2)) { Text(label) }
                    }
                }
            }
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                val modes = listOf(EditorViewModel.Mode.LOSSLESS to "Lossless", EditorViewModel.Mode.SMART to "Smart",
                    EditorViewModel.Mode.REENCODE to "Re-encode")
                modes.forEachIndexed { i, (m, label) ->
                    SegmentedButton(
                        selected = vm.mode == m, onClick = { vm.chooseMode(m) },
                        shape = SegmentedButtonDefaults.itemShape(i, modes.size),
                        enabled = vm.export !is ExportState.Running,
                    ) { Text(label) }
                }
            }
            Text(
                when (vm.mode) {
                    EditorViewModel.Mode.LOSSLESS -> "Every frame is kept unchanged – only its timing changes. No quality loss, but " +
                        "fast parts of slow-motion clips keep their high frame rate, which many players can't show smoothly."
                    EditorViewModel.Mode.SMART -> "Parts that play at the output frame rate are copied unchanged; the others " +
                        "(e.g. real time of a 240 fps recording) are re-encoded to it with the source codec."
                    EditorViewModel.Mode.REENCODE -> "New file at a constant frame rate: slow parts repeat frames, fast parts drop them – plays " +
                        "smoothly everywhere. Hardware encoder; cuts at any frame."
                },
                style = MaterialTheme.typography.bodySmall,
            )
            if (vm.mode == EditorViewModel.Mode.SMART) {
                SmartOptions(vm, info, job as SmartJob)
            } else if (job.hasSegments) {
                Text("Speed sections set the timing: ${edit.segments.size} section(s), the rest in real time. " +
                    "Output ${clock(job.outputDuration.toDouble())} (${speedWords(job.speed.toDouble())} on average).",
                    style = MaterialTheme.typography.bodyMedium)
            }
            if (vm.mode == EditorViewModel.Mode.SMART) {
                // options above
            } else if (lossless) {
                if (!job.hasSegments) {
                    RateDropdown("Frame rate", vm.fps, fpsChoices, { exportFpsLabel(job as LosslessJob, it) }, vm::chooseFps)
                }
            } else {
                RateDropdown("Output frame rate (constant)", vm.fps, fpsChoices, { "${fmtFps(it.toDouble())} fps" }, vm::chooseFps)
                if (!job.hasSegments) {
                    val everyOnce = vm.fps / info.realFps
                    val speeds = listOf<Rational?>(null) + listOf(1L, 2L, 4L, 8L, 16L).map { Rational.of(1, it) }
                    SpeedDropdown(vm.speed, speeds, everyOnce, vm::chooseSpeed)
                }
                if (vm.easy) {
                    Text("Codec ${vm.usedCodec.label} · quality ${vm.usedQuality.label} (Pro: choose them)",
                        style = MaterialTheme.typography.bodySmall)
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        EnumDropdown("Codec", vm.codec, vm.codecs, { it.label }, vm::chooseCodec, Modifier.weight(1f))
                        EnumDropdown("Quality", vm.quality, Quality.entries, { it.label }, vm::chooseQuality, Modifier.weight(1f))
                    }
                }
                val sides = listOf<Int?>(null) + listOf(2160, 1440, 1080, 720, 480)
                    .filter { it < minOf(info.displayWidth, info.displayHeight) }
                EnumDropdown("Resolution", vm.shortSide, sides,
                    { v -> v?.let { "${it}p" } ?: "Like the source (${info.displayWidth}×${info.displayHeight})" },
                    vm::chooseShortSide)
                val r = job as ReencodeJob
                val (w, h) = r.outputSize()
                Text("${w}×$h · ${r.outputFrameCount} frames · ${clock(job.outputDuration.toDouble())} · " +
                    "about ${fmt(r.bitrate / 1e6)} Mbit/s", style = MaterialTheme.typography.bodySmall)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Sound", style = MaterialTheme.typography.bodyLarge)
                    Text(
                        when {
                            info.audio == null -> "This clip has no sound."
                            info.slowmoFactor != null -> "Restored to its real pitch, stretched to the new length"
                            else -> "Stretched to the new length, pitch kept"
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                Switch(checked = vm.sound && info.audio != null, onCheckedChange = { vm.sound = it },
                    enabled = info.audio != null && vm.export !is ExportState.Running)
            }
            when (val e = vm.export) {
                is ExportState.Running -> {
                    LinearProgressIndicator(progress = { e.progress }, modifier = Modifier.fillMaxWidth())
                    OutlinedButton(vm::cancelExport) { Text("Cancel") }
                }
                else -> {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onExport) { Text("Export") }
                        OutlinedButton(vm::addToBatch) { Text("Add to batch") }
                    }
                    if (vm.editingEntry != null) {
                        OutlinedButton(vm::updateBatchEntry) { Text("✔ Update batch entry") }
                    }
                    when (e) {
                        is ExportState.Done -> {
                            Text("Saved ${e.name} in Movies/VideoSpeedControl (${e.frames} frames, ${fmt(e.seconds)} s)")
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button({
                                    ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(e.uri, "video/*")
                                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                                }) { Text("▶ Play") }
                                OutlinedButton({ openOutputFolder(ctx) }) { Text("📁 Open folder") }
                            }
                        }
                        is ExportState.Failed -> Text(e.message, color = MaterialTheme.colorScheme.error)
                        else -> {}
                    }
                }
            }
        }
    }
}

@Composable
fun TreatmentCard(vm: EditorViewModel, onSave: () -> Unit, onLoad: () -> Unit, onShare: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Clip Speed Treatment (.cst)", style = MaterialTheme.typography.titleMedium)
            Text("Sections, trim and export settings of this clip – the same file format as the desktop " +
                "app. A clip speed treatment only loads onto the video it was made for (any file name).",
                style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onSave) { Text("Save") }
                OutlinedButton(onLoad) { Text("Load") }
                OutlinedButton(onShare) { Text("Share") }
            }
        }
    }
}

@Composable
fun BatchCard(vm: EditorViewModel, onAddClip: () -> Unit) {
    val entries = vm.batch
    if (entries.isEmpty()) return
    val ctx = LocalContext.current
    val running = entries.any { it.status == ExportManager.Status.RUNNING || it.status == ExportManager.Status.WAITING }
    val open = entries.count { it.status != ExportManager.Status.DONE }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Batch list", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                TextButton({ openOutputFolder(ctx) }) { Text("📁 Open folder") }
            }
            for (e in entries) {
                val editing = vm.editingEntry == e.task.id
                Row(
                    Modifier.fillMaxWidth()
                        .background(if (editing) MaterialTheme.colorScheme.secondaryContainer else Color.Transparent)
                        .clickable(enabled = !running) { vm.openEntry(e) }
                        .padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(e.task.treatment.sourceName, style = MaterialTheme.typography.bodyMedium,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(e.task.label, style = MaterialTheme.typography.bodySmall)
                        val status = when (e.status) {
                            ExportManager.Status.IDLE -> null
                            ExportManager.Status.WAITING -> "waiting"
                            ExportManager.Status.RUNNING -> "exporting … ${(e.progress * 100).toInt()} %"
                            ExportManager.Status.DONE -> "✔ ${e.output}"
                            ExportManager.Status.FAILED -> "failed: ${e.error}"
                            ExportManager.Status.CANCELLED -> "cancelled"
                        }
                        status?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall,
                                color = when (e.status) {
                                    ExportManager.Status.DONE -> MaterialTheme.colorScheme.primary
                                    ExportManager.Status.FAILED -> MaterialTheme.colorScheme.error
                                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                                })
                        }
                        if (e.status == ExportManager.Status.RUNNING) {
                            LinearProgressIndicator(progress = { e.progress }, modifier = Modifier.fillMaxWidth())
                        }
                    }
                    when (e.status) {
                        ExportManager.Status.RUNNING, ExportManager.Status.WAITING ->
                            TextButton({ vm.cancelBatchEntry(e.task.id) }) { Text("Cancel") }
                        ExportManager.Status.DONE -> {
                            // green when the exported file is still there (it may have been deleted since)
                            val uri = e.outputUri
                            val playable by androidx.compose.runtime.produceState(false, uri) {
                                value = uri != null && kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                    runCatching { ctx.contentResolver.openFileDescriptor(uri, "r")?.use { true } ?: false }
                                        .getOrDefault(false)
                                }
                            }
                            androidx.compose.material3.IconButton({
                                ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "video/*")
                                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                            }, enabled = playable) {
                                Icon(PlayIcon, if (playable) "Play ${e.output}" else "File no longer there",
                                    Modifier.size(30.dp),
                                    tint = if (playable) PlayGreen else MaterialTheme.colorScheme.outline)
                            }
                        }
                        else -> {}
                    }
                    TextButton({ vm.removeBatchEntry(e.task.id) }, enabled = e.status != ExportManager.Status.RUNNING) { Text("✕") }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (running) OutlinedButton(vm::cancelAll) { Text("Cancel all") }
                else Button(vm::exportBatch, enabled = open > 0) { Text("Export batch ($open)") }
                if (entries.any { it.status == ExportManager.Status.DONE }) TextButton(vm::clearDoneEntries) { Text("Remove done") }
            }
            OutlinedButton(onAddClip) { Text("＋ Add another clip") }
            Text("Tap an entry to load it into the editor (e.g. to make another version). Exported entries " +
                "are skipped by the next batch export.", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
fun SmartOptions(vm: EditorViewModel, info: ClipInfo, job: SmartJob) {
    val pieces = vm.smartPieces()
    RateDropdown("Output frame rate", vm.fps, FPS_CHOICES, { "${fmtFps(it.toDouble())} fps" }, vm::chooseFps)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Re-encode everything that does not play at ${fmtFps(vm.fps.toDouble())} fps",
            style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        Switch(checked = vm.smartAuto, onCheckedChange = vm::chooseSmartAuto, enabled = vm.export !is ExportState.Running)
    }
    for (p in pieces) {
        val kind = if (p.rate == info.realFps) "real time" else speedWords((p.rate / info.realFps).toDouble())
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Checkbox(checked = p.reencode, onCheckedChange = { vm.setPieceReencode(p, it) },
                enabled = vm.export !is ExportState.Running)
            Column(Modifier.weight(1f)) {
                Text("Frames ${p.start + 1}–${p.end} · ${fmtFps(p.rate.toDouble())} fps ($kind)",
                    style = MaterialTheme.typography.bodyMedium)
                Text(
                    when {
                        p.reencode -> "re-encoded to ${fmtFps(vm.fps.toDouble())} fps"
                        p.differs -> "copied – keeps ${fmtFps(p.rate.toDouble())} fps (may not play smoothly)"
                        else -> "copied unchanged"
                    },
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
    if (!vm.easy) EnumDropdown("Quality of re-encoded parts", vm.quality, Quality.entries, { it.label }, vm::chooseQuality)
    Text("Codec ${info.codecName}, ${info.width}×${info.height} – always like the source, otherwise the parts " +
        "could not be joined.", style = MaterialTheme.typography.bodySmall)
    val status = when {
        vm.joins == null -> "Analysing the keyframes of this clip …"
        vm.joinsError != null -> "Keyframe analysis failed: ${vm.joinsError}"
        else -> job.blockers().firstOrNull()
    }
    if (status != null) {
        Text(status, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    } else {
        val enc = job.parts.filter { it.encode }
        Text("${job.parts.size} parts, ${enc.size} re-encoded (${enc.sumOf { it.frames }} of ${job.parts.sumOf { it.frames }} frames) · " +
            "output ${clock(job.outputDuration.toDouble())}. Re-encoded parts are widened to the nearest keyframes. " +
            "The file may not play on Apple devices.", style = MaterialTheme.typography.bodySmall)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun <T> EnumDropdown(
    label: String, value: T, choices: List<T>, text: (T) -> String, onChoose: (T) -> Unit,
    modifier: Modifier = Modifier,
) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }, modifier = modifier) {
        OutlinedTextField(
            value = text(value), onValueChange = {}, readOnly = true, singleLine = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
            modifier = Modifier.fillMaxWidth().menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            for (c in choices) DropdownMenuItem(text = { Text(text(c)) }, onClick = { onChoose(c); open = false })
        }
    }
}

@Composable
fun SpeedDropdown(value: Rational?, choices: List<Rational?>, everyOnce: Rational, onChoose: (Rational?) -> Unit) {
    EnumDropdown("Speed", value, choices, { v ->
        when (v) {
            null -> "Every frame once · ${speedWords(everyOnce.toDouble())}"
            else -> speedWords(v.toDouble()) + if (v < everyOnce) " · frames repeat" else ""
        }
    }, onChoose)
}

@Composable
fun ClipInfoCard(info: ClipInfo) {
    val ctx = LocalContext.current
    var open by remember { mutableStateOf(false) }
    val rows = buildList {
        add("File" to info.name)
        add("Size" to if (info.sizeBytes >= 0) Formatter.formatFileSize(ctx, info.sizeBytes) else "unknown")
        add("Codec" to info.codecName)
        add("Resolution" to "${info.displayWidth} × ${info.displayHeight}" +
            if (info.rotation != 0) " (rotated ${info.rotation}°)" else "")
        add("Frame rate" to "${fmtFps(info.fps.toDouble())} fps")
        info.slowmoFactor?.let {
            add("Slow motion" to "recorded at ${fmtFps(info.realFps.toDouble())} fps – plays ${fmt(it)}× slower")
        }
        add("Frames" to "${info.frames.count}")
        add("Duration" to secs(info.durationUs / 1e6))
        add("Keyframes" to "${info.frames.keyframes.size} (every ~${fmt(info.keyframeInterval)} frames)")
        val (lo, hi) = info.frames.frameIntervals()
        if (hi > lo * 1.1 + 1) add("Timing" to "variable frame rate (${lo}–${hi} µs per frame)")
        info.bitrate?.let { add("Bitrate" to "${fmt(it / 1e6)} Mbit/s") }
        add("Colour" to (info.hdr ?: "SDR"))
        add("Audio" to (info.audio ?: "none"))
        info.recorded?.let {
            add("Recorded" to DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withZone(ZoneId.systemDefault()).format(it))
        }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth().clickable { open = !open }, verticalAlignment = Alignment.CenterVertically) {
                Text("Clip info", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Text(if (open) "▲" else "▼")
            }
            if (!open) {
                Text("${info.codecName} · ${info.displayWidth}×${info.displayHeight} · " +
                    (info.slowmoFactor?.let { "${fmtFps(info.realFps.toDouble())} fps slow motion" }
                        ?: "${fmtFps(info.fps.toDouble())} fps") + " · ${info.frames.count} frames",
                    style = MaterialTheme.typography.bodySmall)
            } else for ((k, v) in rows) {
                Row {
                    Text(k, Modifier.weight(0.35f), style = MaterialTheme.typography.labelLarge)
                    Text(v, Modifier.weight(0.65f), style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

/**
 * Transport symbols on a 24-unit grid (28 wide for the key buttons) – the same shapes as the
 * desktop (timeline.transport_icon): |◀ / ▶| with the bar centred on the triangle, "− key" and
 * "key +" close together.
 */
private fun symbol(name: String, width: Float, vararg paths: Pair<String, Boolean>) =
    androidx.compose.ui.graphics.vector.ImageVector.Builder(name, width.dp, 24.dp, width, 24f).apply {
        for ((d, evenOdd) in paths) addPath(androidx.compose.ui.graphics.vector.addPathNodes(d),
            pathFillType = if (evenOdd) androidx.compose.ui.graphics.PathFillType.EvenOdd
            else androidx.compose.ui.graphics.PathFillType.NonZero,
            fill = androidx.compose.ui.graphics.SolidColor(Color.Black))
    }.build()

private fun keyPaths(dx: Float): Array<Pair<String, Boolean>> = arrayOf(
    "M${7 + dx},7.5a4.5,4.5 0 1,0 0,9a4.5,4.5 0 1,0 0,-9z M${7 + dx},10a2,2 0 1,1 0,4a2,2 0 1,1 0,-4z" to true,
    "M${11 + dx},10.9h11v2.2h-11z M${18.5 + dx},13h2.2v3.5h-2.2z M${15 + dx},13h2.2v2.5h-2.2z" to false,
)

val KeyMinusIcon by lazy { symbol("KeyMinus", 28f, "M1,10.9h5.5v2.2h-5.5z" to false, *keyPaths(5f)) }
val KeyPlusIcon by lazy { symbol("KeyPlus", 28f, *keyPaths(-2f), "M21.5,10.9h5.5v2.2h-5.5z M23.15,9.25h2.2v5.5h-2.2z" to false) }
val FirstIcon by lazy { symbol("First", 24f, "M5,6h2.4v12h-2.4z M19,6v12l-10.5,-6z" to false) }
val LastIcon by lazy { symbol("Last", 24f, "M16.6,6h2.4v12h-2.4z M5,6v12l10.5,-6z" to false) }

/**
 * Show the export folder (Movies/VideoSpeedControl) in the system's Files app. Android has no
 * general "open folder" – the Files app (DocumentsUI) accepts its document URI with the
 * directory type; without it, a message.
 */
fun openOutputFolder(ctx: android.content.Context) {
    val folder = android.provider.DocumentsContract.buildDocumentUri(
        "com.android.externalstorage.documents", "primary:" + com.alexvulcu.videospeedcontrol.core.OutputStore.RELATIVE_PATH.trimEnd('/'))
    val intent = Intent(Intent.ACTION_VIEW)
        .setDataAndType(folder, android.provider.DocumentsContract.Document.MIME_TYPE_DIR)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    try {
        ctx.startActivity(intent)
    } catch (e: android.content.ActivityNotFoundException) {
        android.widget.Toast.makeText(ctx, "No file manager found – the exports are in " +
            com.alexvulcu.videospeedcontrol.core.OutputStore.RELATIVE_PATH, android.widget.Toast.LENGTH_LONG).show()
    }
}

/** Play symbol (batch list), green while the file can be played. */
val PlayGreen = Color(0xFF34C759)

val PlayIcon: androidx.compose.ui.graphics.vector.ImageVector by lazy {
    androidx.compose.ui.graphics.vector.ImageVector.Builder("Play", 24.dp, 24.dp, 24f, 24f).apply {
        addPath(androidx.compose.ui.graphics.vector.addPathNodes("M7,4.5v15l12.5,-7.5z"),
            fill = androidx.compose.ui.graphics.SolidColor(Color.Black))
    }.build()
}
