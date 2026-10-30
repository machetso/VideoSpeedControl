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
import androidx.compose.material3.ButtonDefaults
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
import androidx.compose.ui.draw.clip
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
            Image(it.asImageBitmap(), contentDescription = tr("Frame %d", vm.playhead + 1),
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
    val outT = if (inRange) secs(Segments.outputTime(job.pieces(), p).toDouble()) else tr("cut")
    val key = if (p in fm.keyframes) tr(" · keyframe") else ""
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (!vm.easy) Text(tr("Frame %d / %d%s · source %s · output %s", p + 1, fm.count, key, secs((fm.ptsUs[p] - fm.ptsUs[0]) / 1e6), outT),
            style = MaterialTheme.typography.bodySmall)
        else {
            // the yellow brackets as times: in, out and what is kept
            val tIn = vm.realSeconds(edit, edit.trim.start)
            val tOut = vm.realSeconds(edit, edit.trimEnd)
            Text(tr("In %s · Out %s · ⏳ %s", secs1(tIn), secs1(tOut), secs1(tOut - tIn)), style = MaterialTheme.typography.bodyMedium)
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Button(vm::togglePlay) { Text(if (vm.playing) tr("■ Stop") else tr("▶ Play preview")) }
            Text(
                "  ${clock(job.outputDuration.toDouble())} · ${speedWords(job.speed.toDouble())}" +
                    if (job.hasSegments) tr(" on average") else "",
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f),
            )
            FilterChip(selected = vm.magnet, onClick = vm::toggleMagnet, label = { Text("🧲") })
        }
        Text(
            if (vm.proxyProgress < 1f) tr("Preparing frames for exact scrubbing… %d %%", (vm.proxyProgress * 100).toInt())
            else tr("Drag on the picture to move frame by frame."),
            style = MaterialTheme.typography.bodySmall,
        )
        // start of clip · previous keyframe · one frame back / ahead · next keyframe · end of clip
        // (left-to-right in every language, like the timeline)
        androidx.compose.runtime.CompositionLocalProvider(
            androidx.compose.ui.platform.LocalLayoutDirection provides androidx.compose.ui.unit.LayoutDirection.Ltr) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            val pad = PaddingValues(horizontal = 6.dp)
            FilledTonalButton(vm::toStart, contentPadding = pad) { Icon(FirstIcon, tr("first frame"), Modifier.size(22.dp)) }
            if (!vm.easy) FilledTonalButton(vm::previousKeyframe, contentPadding = pad) {
                Icon(KeyMinusIcon, tr("previous keyframe"), Modifier.size(width = 30.dp, height = 26.dp))
            }
            FilledTonalButton({ vm.step(-1) }, contentPadding = pad) { Text("◀ 1") }
            FilledTonalButton({ vm.step(1) }, contentPadding = pad) { Text("1 ▶") }
            if (!vm.easy) FilledTonalButton(vm::nextKeyframe, contentPadding = pad) {
                Icon(KeyPlusIcon, tr("next keyframe"), Modifier.size(width = 30.dp, height = 26.dp))
            }
            FilledTonalButton(vm::toEnd, contentPadding = pad) { Icon(LastIcon, tr("last frame"), Modifier.size(22.dp)) }
        }
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
    if (vm.easy && vm.wholeClip) {
        // Easy "Whole clip": one speed for everything, the sections are kept aside
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(tr("Whole clip selected"), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    TextButton(vm::undo, enabled = edit.undo.isNotEmpty()) {
                        Text(if (edit.undo.isEmpty()) tr("↶ Undo") else tr("↶ Undo (%d)", edit.undo.size))
                    }
                    TextButton(vm::redo, enabled = edit.redo.isNotEmpty()) {
                        Text(if (edit.redo.isEmpty()) tr("↷ Redo") else tr("↷ Redo (%d)", edit.redo.size))
                    }
                }
                OutlinedButton({ vm.chooseWholeClip(false) }) { Text(tr("Back to Clip Sections")) }
                RateDropdown(tr("Video speed"), vm.wholeRate ?: vm.fps, easyRates(real, vm.fps),
                    { easySpeedLabel(real, vm.fps, it) }, vm::chooseWholeRate)
            }
        }
        return
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(tr("Clip Sections"), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                TextButton(vm::undo, enabled = edit.undo.isNotEmpty()) {
                    Text(if (edit.undo.isEmpty()) tr("↶ Undo") else tr("↶ Undo (%d)", edit.undo.size))
                }
                TextButton(vm::redo, enabled = edit.redo.isNotEmpty()) {
                    Text(if (edit.redo.isEmpty()) tr("↷ Redo") else tr("↷ Redo (%d)", edit.redo.size))
                }
            }
            if (!vm.easy) edit.undo.lastOrNull()?.let {
                Text(tr("Last change: %s", it.what), style = MaterialTheme.typography.bodySmall,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            val selected = edit.segments.getOrNull(vm.selectedSection)
            selected?.let { SectionEditor(vm, edit, vm.selectedSection, rates) }
            // Easy: while a section is open its own "Video speed" is enough
            if (vm.easy && selected == null) RateDropdown(tr("Video speed of new sections"), vm.sectionFps, easyRates(real, vm.fps),
                { easySpeedLabel(real, vm.fps, it) }, vm::chooseSectionFps)
            else if (!vm.easy) RateDropdown(tr("New sections play at"), vm.sectionFps, rates, { sectionFpsLabel(real, it) },
                vm::chooseSectionFps)
            val start = vm.pendingStart
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                val pad = if (vm.easy) PaddingValues(horizontal = 14.dp) else ButtonDefaults.ContentPadding
                Button(vm::markStart, contentPadding = pad) { Text(tr("[ Start")) }
                Button(vm::markEnd, contentPadding = pad) { Text(tr("End ]")) }
                if (vm.easy) OutlinedButton({ vm.chooseWholeClip(true) }, contentPadding = pad) { Text(tr("Whole clip")) }
                if (start != null) {
                    TextButton(vm::cancelMark) { Text(tr("Cancel")) }
                }
            }
            if (!vm.easy) {
                val from = start ?: edit.quickStart(vm.playhead)
                Text(
                    if (start != null) tr("Start at frame %d – now move to the last frame and tap “End”.", start + 1)
                    else tr("Move to the last frame of a section and tap “End”: the section starts right after the " +
                        "one before it – the first one at the start of the clip (here: frame %d). So for a " +
                        "second section just tap “End” again. Tap “Start” first only if a section should begin elsewhere.", from + 1),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (edit.segments.isNotEmpty()) {
                HorizontalDivider()
                if (!vm.easy) Text(tr("Tap a section (here or on the timeline) to edit it; drag a border on the timeline " +
                    "to move it."), style = MaterialTheme.typography.bodySmall)
            }
            edit.segments.forEachIndexed { i, s ->
                val len = (Rational.of((s.end - s.start).toLong()) / s.fps).toDouble()
                val bg = if (i == vm.selectedSection) MaterialTheme.colorScheme.secondaryContainer else Color.Transparent
                Row(Modifier.fillMaxWidth().background(bg).clickable { vm.selectSection(i) }.padding(6.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        if (vm.easy) {
                            Text(tr("Section %d: ⏳ %s", i + 1, secs1(len)), style = MaterialTheme.typography.bodyMedium)
                            Text(easySpeedLabel(real, vm.fps, s.fps), style = MaterialTheme.typography.bodySmall)
                        } else {
                            Text(tr("Frames %d–%d · plays %s", s.start + 1, s.end, secs(len)), style = MaterialTheme.typography.bodyMedium)
                            Text(sectionFpsLabel(real, s.fps) + smoothNote(s), style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    Text(tr("Edit ›"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                }
            }
            if (edit.segments.isNotEmpty()) {
                TextButton({ confirmClear = true }) { Text(tr("Clear sections")) }
            }
        }
    }
    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text(tr("Clear all sections?")) },
            text = { Text(tr("All %d clip sections of this clip are removed. You can undo this.", edit.segments.size)) },
            confirmButton = { TextButton({ vm.clearSections(); confirmClear = false }) { Text(tr("Clear")) } },
            dismissButton = { TextButton({ confirmClear = false }) { Text(tr("Keep")) } },
        )
    }
}

private fun smoothNote(s: com.alexvulcu.videospeedcontrol.core.Segment): String = when {
    s.smoothStart && s.smoothEnd -> tr(" · smooth in and out")
    s.smoothStart -> tr(" · smooth in")
    s.smoothEnd -> tr(" · smooth out")
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
                Text(if (vm.easy) tr("Section %d: ⏳ %s", index + 1, secs1(len))
                    else tr("Section %d: frames %d–%d · plays %s", index + 1, s.start + 1, s.end, secs(len)),
                    style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                TextButton(vm::deselectSection) { Text(tr("Done")) }
            }
            if (vm.easy) {
                RateDropdown(tr("Video speed"), s.fps, easyRates(real, vm.fps), { easySpeedLabel(real, vm.fps, it) }, { vm.setSectionFps(index, it) })
            } else {
                RateDropdown(tr("Frame rate"), s.fps, rates, { sectionFpsLabel(real, it) }, { vm.setSectionFps(index, it) })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton({ vm.setSectionStartHere(index) }) { Text(tr("Start = playhead")) }
                    OutlinedButton({ vm.setSectionEndHere(index) }) { Text(tr("End = playhead")) }
                }
            }
            for (atStart in if (vm.easy) emptyList() else listOf(true, false)) {
                val other = edit.neighbourRate(index, atStart)
                val on = if (atStart) s.smoothStart else s.smoothEnd
                val possible = other != null && other != s.fps
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (atStart) tr("Smooth transition in") else tr("Smooth transition out"),
                            style = MaterialTheme.typography.bodyMedium)
                        Text(
                            when {
                                other == null -> if (atStart) tr("Starts with the clip") else tr("Ends with the clip")
                                !possible -> tr("Same speed on the other side")
                                else -> {
                                    val a = speedWords((if (atStart) other / real else s.fps / real).toDouble())
                                    val b = speedWords((if (atStart) s.fps / real else other / real).toDouble())
                                    tr("%s → %s, changing evenly over 0.5 s", a, b)
                                }
                            },
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Switch(on, { vm.setSmooth(index, atStart, it) }, enabled = possible || on)
                }
            }
            TextButton({ vm.removeSection(index) }) { Text(tr("Remove section"), color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
fun TrimPanel(vm: EditorViewModel, edit: ClipEdit) {
    val count = edit.info.frames.count
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(if (vm.easy) tr("Clip length") else tr("Trim"), style = MaterialTheme.typography.titleMedium)
            val whole = edit.trim.start == 0 && edit.trim.end == null
            Text(
                if (vm.easy) {
                    // real-time length of the kept part (the yellow brackets on the timeline)
                    val pts = edit.info.frames.ptsUs
                    fun t(f: Int) = (if (f < pts.size) pts[f] else pts.last() + (pts.last() - pts[maxOf(0, pts.size - 2)])) / 1e6
                    val k = (edit.info.realFps / edit.info.fps).toDouble()
                    val len = (t(edit.trimEnd) - t(edit.trim.start)) / k
                    val all = (t(count) - t(0)) / k
                    if (whole) tr("⏳ %s – the whole clip", secs1(len)) else tr("⏳ %s of %s", secs1(len), secs1(all))
                } else if (whole) tr("Whole clip (frames 1–%d)", count)
                else tr("Frames %d–%d of %d", edit.trim.start + 1, edit.trimEnd, count),
                style = MaterialTheme.typography.bodyMedium,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(vm::setIn) { Text(tr("Set in")) }
                OutlinedButton(vm::setOut) { Text(tr("Set out")) }
                TextButton(vm::clearTrim, enabled = edit.trim.start != 0 || edit.trim.end != null) { Text(tr("Reset")) }
            }
            if (!vm.easy) Text(
                if (vm.snapsToKeyframes)
                    tr("Lossless and smart export can only cut at keyframes (the ticks under the timeline): only they are " +
                        "complete pictures, all other frames store differences to their neighbours. In and out " +
                        "snap to the nearest keyframe.")
                else tr("Re-encoding cuts at any frame."),
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
                Text(if (vm.easy) tr("Save") else tr("Export"), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                // Easy hides the codec details (codec, quality); Pro shows everything
                SingleChoiceSegmentedButtonRow {
                    listOf(true to "Easy", false to "Pro").forEachIndexed { i, (easy, label) ->
                        SegmentedButton(selected = vm.easy == easy, onClick = { vm.chooseEasy(easy) },
                            shape = SegmentedButtonDefaults.itemShape(i, 2), colors = greenSegments()) { Text(tr(label)) }
                    }
                }
            }
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                val modes = listOf(EditorViewModel.Mode.LOSSLESS to "Lossless", EditorViewModel.Mode.SMART to "Smart",
                    EditorViewModel.Mode.REENCODE to "Re-encode")
                modes.forEachIndexed { i, (m, label) ->
                    SegmentedButton(
                        selected = vm.mode == m, onClick = { vm.chooseMode(m) },
                        shape = SegmentedButtonDefaults.itemShape(i, modes.size), colors = greenSegments(),
                        enabled = vm.export !is ExportState.Running,
                    ) { Text(tr(label)) }
                }
            }
            Text(
                when (vm.mode) {
                    EditorViewModel.Mode.LOSSLESS -> if (vm.easy) tr("The video as a whole stays unchanged – only the speed of the sections changes. " +
                        "No quality loss, but it probably won't play on every device.")
                        else tr("Every frame is kept unchanged – only its timing changes. No quality loss, but " +
                        "fast parts of slow-motion clips keep their high frame rate, which many players can't show smoothly.")
                    EditorViewModel.Mode.SMART -> if (vm.easy) tr("Only the parts of the video that need it are recalculated.")
                        else tr("Parts that play at the output frame rate are copied unchanged; the others " +
                        "(e.g. real time of a 240 fps recording) are re-encoded to it with the source codec.")
                    EditorViewModel.Mode.REENCODE -> if (vm.easy) tr("The whole video, with the changed sections, is saved as a new file.")
                        else tr("New file at a constant frame rate: slow parts repeat frames, fast parts drop them – plays " +
                        "smoothly everywhere. Hardware encoder; cuts at any frame.")
                },
                style = MaterialTheme.typography.bodySmall,
            )
            if (vm.mode == EditorViewModel.Mode.SMART) {
                SmartOptions(vm, info, job as SmartJob)
            } else if (job.hasSegments && !vm.easy) {
                Text(trp("Clip sections set the timing: %d section, the rest in real time. Output %s (%s on average).",
                    "Clip sections set the timing: %d sections, the rest in real time. Output %s (%s on average).",
                    edit.segments.size, edit.segments.size, clock(job.outputDuration.toDouble()), speedWords(job.speed.toDouble())),
                    style = MaterialTheme.typography.bodyMedium)
            }
            if (vm.mode == EditorViewModel.Mode.SMART) {
                // options above
            } else if (lossless) {
                if (!job.hasSegments) {
                    if (vm.easy) RateDropdown(tr("Output frame rate"), vm.fps, fpsChoices, { "${fmtFps(it.toDouble())} fps" }, vm::chooseFps)
                    else RateDropdown(tr("Frame rate"), vm.fps, fpsChoices, { exportFpsLabel(job as LosslessJob, it) }, vm::chooseFps)
                }
            } else {
                RateDropdown(tr("Output frame rate"), vm.fps, fpsChoices, { "${fmtFps(it.toDouble())} fps" }, vm::chooseFps)
                if (!job.hasSegments && !vm.easy) {          // Easy: the speed comes from the clip sections
                    val everyOnce = vm.fps / info.realFps
                    val speeds = listOf<Rational?>(null) + listOf(1L, 2L, 4L, 8L, 16L).map { Rational.of(1, it) }
                    SpeedDropdown(vm.speed, speeds, everyOnce, vm::chooseSpeed)
                }
                if (!vm.easy) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        EnumDropdown(tr("Codec"), vm.codec, vm.codecs, { tr(it.label) }, vm::chooseCodec, Modifier.weight(1f))
                        EnumDropdown(tr("Quality"), vm.quality, Quality.entries, { tr(it.label) }, vm::chooseQuality, Modifier.weight(1f))
                    }
                }
                val sides = listOf<Int?>(null) + listOf(2160, 1440, 1080, 720, 480)
                    .filter { it < minOf(info.displayWidth, info.displayHeight) }
                EnumDropdown(tr("Resolution"), vm.shortSide, sides,
                    { v -> v?.let { "${it}p" } ?: tr("No change (%d×%d)", info.displayWidth, info.displayHeight) },
                    vm::chooseShortSide)
                val r = job as ReencodeJob
                val (w, h) = r.outputSize()
                Text(tr("%d×%d · %d frames · %s · about %s Mbit/s", w, h, r.outputFrameCount,
                    clock(job.outputDuration.toDouble()), fmt(r.bitrate / 1e6)), style = MaterialTheme.typography.bodySmall)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(tr("Sound"), style = MaterialTheme.typography.bodyLarge)
                    if (!vm.easy) Text(
                        when {
                            info.audio == null -> tr("This clip has no sound.")
                            info.slowmoFactor != null -> tr("Restored to its real pitch, stretched to the new length")
                            else -> tr("Stretched to the new length, pitch kept")
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                Switch(checked = vm.sound && info.audio != null, onCheckedChange = { vm.sound = it }, colors = greenSwitch(),
                    enabled = info.audio != null && vm.export !is ExportState.Running)
            }
            when (val e = vm.export) {
                is ExportState.Running -> {
                    // the file only appears in the folder (and in Google Photos) once it is complete
                    Text(tr("Still saving … %d %% – the video appears in Movies/VideoSpeedControl when it is finished.",
                        (e.progress * 100).toInt()), style = MaterialTheme.typography.bodyMedium)
                    LinearProgressIndicator(progress = { e.progress }, modifier = Modifier.fillMaxWidth())
                    OutlinedButton(vm::cancelExport) { Text(tr("Cancel")) }
                }
                else -> {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onExport) { Text(if (vm.easy) tr("Save video") else tr("Export")) }
                        OutlinedButton(vm::addToBatch) { Text(if (vm.easy) tr("Add as new version") else tr("Add to batch")) }
                    }
                    if (vm.editingEntry != null && !vm.easy) {      // Easy: only "Add as new version"
                        OutlinedButton(vm::updateBatchEntry) { Text(tr("✔ Save changes to this entry")) }
                    }
                    when (e) {
                        is ExportState.Done -> {
                            Text(tr("Saved %s in Movies/VideoSpeedControl (%d frames, %s s)", e.name, e.frames, fmt(e.seconds)))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button({
                                    ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(e.uri, "video/*")
                                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                                }) { Text(tr("▶ Play")) }
                                OutlinedButton({ openOutputFolder(ctx) }) { Text(tr("📁 Open folder")) }
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
            Text(tr("Clip Speed Treatment (.cst)"), style = MaterialTheme.typography.titleMedium)
            Text(if (vm.easy) tr("A Clip Speed Treatment saves all planned edits of a video clip (sections, trims, " +
                "different speeds), so you can change them again later.")
                else tr("Sections, trim and export settings of this clip – the same file format as the desktop " +
                "app. “Save” puts it in Documents/VideoSpeedControl/Clip Speed Treatments. It only loads onto " +
                "the video it was made for (any file name)."),
                style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onSave) { Text(tr("Save")) }
                OutlinedButton(onLoad) { Text(tr("Load")) }
                OutlinedButton(onShare) { Text(tr("Share")) }
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
                Text(tr("Batch list"), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                TextButton({ openOutputFolder(ctx) }) { Text(tr("📁 Open folder")) }
            }
            var infoFor by remember { mutableStateOf<ExportManager.Entry?>(null) }
            for (e in entries) {
                val editing = vm.editingEntry == e.task.id
                // tidy row (user): a picture of the video and its mode; the details behind ⓘ
                Row(
                    Modifier.fillMaxWidth()
                        .background(if (editing) MaterialTheme.colorScheme.secondaryContainer else Color.Transparent)
                        .clickable(enabled = !running) { vm.openEntry(e) }
                        .padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    BatchThumb(e)
                    Column(Modifier.weight(1f)) {
                        Text(when (e.task.treatment.settings.mode) {
                            com.alexvulcu.videospeedcontrol.core.Treatment.Mode.LOSSLESS -> tr("Lossless")
                            com.alexvulcu.videospeedcontrol.core.Treatment.Mode.SMART -> tr("Smart")
                            com.alexvulcu.videospeedcontrol.core.Treatment.Mode.REENCODE -> tr("Re-encode")
                        }, style = MaterialTheme.typography.bodyMedium)
                        when (e.status) {
                            ExportManager.Status.RUNNING -> {
                                Text(tr("still saving … %d %%", (e.progress * 100).toInt()), style = MaterialTheme.typography.bodySmall)
                                LinearProgressIndicator(progress = { e.progress }, modifier = Modifier.fillMaxWidth())
                            }
                            ExportManager.Status.WAITING -> Text(tr("waiting"), style = MaterialTheme.typography.bodySmall)
                            ExportManager.Status.FAILED -> Text(tr("failed – see ⓘ"), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error)
                            else -> {}
                        }
                    }
                    if (e.status == ExportManager.Status.DONE) {
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
                            Icon(PlayIcon, if (playable) tr("Play %s", e.output) else tr("File no longer there"),
                                Modifier.size(30.dp), tint = if (playable) PlayGreen else MaterialTheme.colorScheme.outline)
                        }
                    }
                    androidx.compose.material3.IconButton({ infoFor = e }) { Text("ⓘ", style = MaterialTheme.typography.titleLarge) }
                    if (e.status == ExportManager.Status.RUNNING || e.status == ExportManager.Status.WAITING)
                        TextButton({ vm.cancelBatchEntry(e.task.id) }) { Text(tr("Cancel")) }
                    else TextButton({ vm.removeBatchEntry(e.task.id) }) { Text("✕") }
                }
            }
            infoFor?.let { e ->
                AlertDialog(
                    onDismissRequest = { infoFor = null },
                    title = { Text(e.task.treatment.sourceName) },
                    text = {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(e.task.label)
                            Text(when (e.status) {
                                ExportManager.Status.DONE -> tr("Saved as %s in Movies/VideoSpeedControl", e.output)
                                ExportManager.Status.FAILED -> tr("Failed: %s", e.error)
                                ExportManager.Status.RUNNING -> tr("Still saving … %d %%", (e.progress * 100).toInt())
                                ExportManager.Status.WAITING -> tr("Waiting to be saved")
                                ExportManager.Status.CANCELLED -> tr("Cancelled")
                                ExportManager.Status.IDLE -> tr("Not saved yet")
                            })
                            Text(tr("Tap the entry to open it in the editor, e.g. to make another version."),
                                style = MaterialTheme.typography.bodySmall)
                        }
                    },
                    confirmButton = { TextButton({ infoFor = null }) { Text(tr("OK")) } },
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (running) OutlinedButton(vm::cancelAll) { Text(tr("Cancel all")) }
                else Button(vm::exportBatch, enabled = open > 0) { Text(if (vm.easy) tr("Save all (%d)", open) else tr("Export batch (%d)", open)) }
                if (entries.any { it.status == ExportManager.Status.DONE }) TextButton(vm::clearDoneEntries) { Text(tr("Remove done")) }
            }
            OutlinedButton(onAddClip) { Text(tr("＋ Add another clip")) }
            if (!vm.easy) Text(tr("Tap an entry to load it into the editor (e.g. to make another version). Exported entries " +
                "are skipped by the next batch export."), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
fun SmartOptions(vm: EditorViewModel, info: ClipInfo, job: SmartJob) {
    val pieces = vm.smartPieces()
    RateDropdown(tr("Output frame rate"), vm.fps, FPS_CHOICES, { "${fmtFps(it.toDouble())} fps" }, vm::chooseFps)
    if (!vm.easy) Row(verticalAlignment = Alignment.CenterVertically) {
        Text(tr("Re-encode everything that does not play at %s fps", fmtFps(vm.fps.toDouble())),
            style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        Switch(checked = vm.smartAuto, onCheckedChange = vm::chooseSmartAuto, enabled = vm.export !is ExportState.Running,
            colors = greenSwitch())
    }
    for (p in if (vm.easy) emptyList() else pieces) {
        val kind = if (p.rate == info.realFps) tr("real time") else speedWords((p.rate / info.realFps).toDouble())
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Checkbox(checked = p.reencode, onCheckedChange = { vm.setPieceReencode(p, it) },
                enabled = vm.export !is ExportState.Running)
            Column(Modifier.weight(1f)) {
                Text(tr("Frames %d–%d · %s fps (%s)", p.start + 1, p.end, fmtFps(p.rate.toDouble()), kind),
                    style = MaterialTheme.typography.bodyMedium)
                Text(
                    when {
                        p.reencode -> tr("re-encoded to %s fps", fmtFps(vm.fps.toDouble()))
                        p.differs -> tr("copied – keeps %s fps (may not play smoothly)", fmtFps(p.rate.toDouble()))
                        else -> tr("copied unchanged")
                    },
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
    if (!vm.easy) EnumDropdown(tr("Quality of re-encoded parts"), vm.quality, Quality.entries, { tr(it.label) }, vm::chooseQuality)
    if (!vm.easy) Text(tr("Codec %s, %d×%d – always like the source, otherwise the parts could not be joined.",
        info.codecName, info.width, info.height), style = MaterialTheme.typography.bodySmall)
    val status = when {
        vm.joins == null -> tr("Analysing the keyframes of this clip …")
        vm.joinsError != null -> tr("Keyframe analysis failed: %s", vm.joinsError)
        else -> job.blockers().firstOrNull()
    }
    if (status != null) {
        Text(status, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    } else if (!vm.easy) {
        val enc = job.parts.filter { it.encode }
        Text(tr("%d parts, %d re-encoded (%d of %d frames) · output %s. Re-encoded parts are widened to the nearest " +
            "keyframes. The file may not play on Apple devices.", job.parts.size, enc.size, enc.sumOf { it.frames },
            job.parts.sumOf { it.frames }, clock(job.outputDuration.toDouble())), style = MaterialTheme.typography.bodySmall)
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
    EnumDropdown(tr("Speed"), value, choices, { v ->
        when (v) {
            null -> tr("Every frame once · %s", speedWords(everyOnce.toDouble()))
            else -> speedWords(v.toDouble()) + if (v < everyOnce) tr(" · frames repeat") else ""
        }
    }, onChoose)
}

@Composable
fun ClipInfoCard(info: ClipInfo) {
    val ctx = LocalContext.current
    var open by remember { mutableStateOf(false) }
    val rows = buildList {
        add(tr("File") to info.name)
        add(tr("Size") to if (info.sizeBytes >= 0) Formatter.formatFileSize(ctx, info.sizeBytes) else tr("unknown"))
        add(tr("Codec") to info.codecName)
        add(tr("Resolution") to "${info.displayWidth} × ${info.displayHeight}" +
            if (info.rotation != 0) tr(" (rotated %d°)", info.rotation) else "")
        add(tr("Frame rate") to "${fmtFps(info.fps.toDouble())} fps")
        info.slowmoFactor?.let {
            add(tr("Slow motion") to tr("recorded at %s fps – plays %s× slower", fmtFps(info.realFps.toDouble()), fmt(it)))
        }
        add(tr("Frames") to "${info.frames.count}")
        add(tr("Duration") to secs(info.durationUs / 1e6))
        add(tr("Keyframes") to tr("%d (every ~%s frames)", info.frames.keyframes.size, fmt(info.keyframeInterval)))
        val (lo, hi) = info.frames.frameIntervals()
        if (hi > lo * 1.1 + 1) add(tr("Timing") to tr("variable frame rate (%d–%d µs per frame)", lo, hi))
        info.bitrate?.let { add(tr("Bitrate") to "${fmt(it / 1e6)} Mbit/s") }
        add(tr("Colour") to (info.hdr ?: "SDR"))
        add(tr("Audio") to (info.audio ?: tr("none")))
        info.recorded?.let {
            add(tr("Recorded") to DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withZone(ZoneId.systemDefault()).format(it))
        }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth().clickable { open = !open }, verticalAlignment = Alignment.CenterVertically) {
                Text(tr("Clip info"), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Text(if (open) "▲" else "▼")
            }
            if (!open) {
                Text("${info.codecName} · ${info.displayWidth}×${info.displayHeight} · " +
                    (info.slowmoFactor?.let { tr("%s fps slow motion", fmtFps(info.realFps.toDouble())) }
                        ?: "${fmtFps(info.fps.toDouble())} fps") + tr(" · %d frames", info.frames.count),
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
fun openOutputFolder(ctx: android.content.Context) =
    openFolder(ctx, com.alexvulcu.videospeedcontrol.core.OutputStore.RELATIVE_PATH)

/** Shows Documents / Movies sub-folder [relativePath] ("Movies/VideoSpeedControl/") in the Files app. */
fun openFolder(ctx: android.content.Context, relativePath: String) {
    val folder = android.provider.DocumentsContract.buildDocumentUri(
        "com.android.externalstorage.documents", "primary:" + relativePath.trimEnd('/'))
    val intent = Intent(Intent.ACTION_VIEW)
        .setDataAndType(folder, android.provider.DocumentsContract.Document.MIME_TYPE_DIR)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    try {
        ctx.startActivity(intent)
    } catch (e: android.content.ActivityNotFoundException) {
        android.widget.Toast.makeText(ctx, tr("No file manager found – the folder is %s", relativePath),
            android.widget.Toast.LENGTH_LONG).show()
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

/** Chosen options are green (user): segmented buttons and switches that are on. */
val ChosenGreen = Color(0xFF2E9E4F)

@Composable
fun greenSegments() = SegmentedButtonDefaults.colors(
    activeContainerColor = ChosenGreen, activeContentColor = Color.White, activeBorderColor = ChosenGreen)

@Composable
fun greenSwitch() = androidx.compose.material3.SwitchDefaults.colors(
    checkedTrackColor = ChosenGreen, checkedThumbColor = Color.White, checkedBorderColor = ChosenGreen)

/** Picture of a batch entry's video (system thumbnail, else the frame at its trim start). */
@Composable
private fun BatchThumb(e: ExportManager.Entry) {
    val ctx = LocalContext.current
    val uri = e.task.uri
    val bmp by androidx.compose.runtime.produceState<android.graphics.Bitmap?>(null, uri) {
        value = Gallery.thumbnail(ctx, uri) ?: kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            runCatching {
                val mmr = android.media.MediaMetadataRetriever()
                try {
                    mmr.setDataSource(ctx, uri)
                    mmr.getScaledFrameAtTime(0, android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC, 256, 256)
                } finally { mmr.release() }
            }.getOrNull()
        }
    }
    Box(Modifier.size(64.dp).background(MaterialTheme.colorScheme.surfaceVariant,
        androidx.compose.foundation.shape.RoundedCornerShape(6.dp))) {
        bmp?.let {
            Image(it.asImageBitmap(), null, Modifier.fillMaxSize().clip(androidx.compose.foundation.shape.RoundedCornerShape(6.dp)),
                contentScale = ContentScale.Crop)
        }
    }
}
