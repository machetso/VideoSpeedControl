package com.alexvulcu.videospeedcontrol.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.alexvulcu.videospeedcontrol.R
import com.alexvulcu.videospeedcontrol.core.CstStore
import com.alexvulcu.videospeedcontrol.core.OutputStore

private const val EASY_INFO = "Everything for quick results: clip sections with a simple video speed " +
    "(“4× slower”), speed changes always smoothed, the yellow brackets on the timeline to cut, and " +
    "“Save video”. Smart re-encode keeps the source codec, re-encode uses AV1 (fast) in high quality."

private const val PRO_INFO = "Everything in Easy, plus: frame rates and frame numbers, codec (AV1 fast / best, " +
    "HEVC, H.264) and quality, a speed for re-encoding without sections, smooth transitions chosen per " +
    "border, section start / end at the playhead, keyframe buttons, choosing which parts smart re-encode " +
    "re-encodes, the trim card with in / out buttons, and saving changes back into a batch entry."

/** Menu behind the logo (user, 0.93): Easy / Pro with what each can do, the folders, the preview cache. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppMenu(vm: EditorViewModel, onClose: () -> Unit) {
    val ctx = LocalContext.current
    var confirmDelete by remember { mutableStateOf(false) }
    var refresh by remember { mutableStateOf(0) }
    val bytes by produceState(-1L, refresh) { value = vm.previewBytes() }
    val version = remember {
        runCatching { ctx.packageManager.getPackageInfo(ctx.packageName, 0).versionName }.getOrNull() ?: ""
    }
    ModalBottomSheet(onDismissRequest = onClose,
        sheetState = androidx.compose.material3.rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).navigationBarsPadding()
                .padding(horizontal = 20.dp, vertical = 4.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Image(painterResource(R.drawable.vsc_logo), null, Modifier.size(44.dp))
                Column {
                    Text(tr("VideoSpeedControl"), style = MaterialTheme.typography.titleLarge)
                    Text(tr("Version %s", version), style = MaterialTheme.typography.bodySmall)
                }
            }

            Text(tr("Mode"), style = MaterialTheme.typography.titleMedium)
            ModeChoice(tr("Easy"), tr(EASY_INFO), selected = vm.easy) { vm.chooseEasy(true) }
            ModeChoice(tr("Pro"), tr(PRO_INFO), selected = !vm.easy) { vm.chooseEasy(false) }

            HorizontalDivider()
            // the phone's language by default; the choice is kept across restarts
            Text("Language / Sprache", style = MaterialTheme.typography.titleMedium)
            // every dictionary in i18n/ is offered (in its own language)
            val choices = listOf(I18n.SYSTEM to tr("Phone language (%s)",
                java.util.Locale.getDefault().getDisplayLanguage(java.util.Locale.getDefault()) +
                    if (I18n.phoneLanguage == null) " → English" else "")) +
                I18n.languages.map { it.code to languageLabel(it) }
            for ((code, label) in choices) {
                Row(Modifier.fillMaxWidth().clickable { I18n.choose(ctx, code) }, verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(I18n.choice == code || (code == I18n.SYSTEM && I18n.languages.none { it.code == I18n.choice }),
                        { I18n.choose(ctx, code) }, colors = RadioButtonDefaults.colors(selectedColor = ChosenGreen))
                    Text(label, style = MaterialTheme.typography.bodyLarge)
                }
            }

            HorizontalDivider()
            Text(tr("Folders"), style = MaterialTheme.typography.titleMedium)
            FolderRow(tr("Saved videos"), OutputStore.RELATIVE_PATH.trimEnd('/')) { openFolder(ctx, OutputStore.RELATIVE_PATH) }
            FolderRow(tr("Clip Speed Treatments (.cst)"), CstStore.RELATIVE_PATH.trimEnd('/')) { openFolder(ctx, CstStore.RELATIVE_PATH) }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(tr("Previews"), style = MaterialTheme.typography.bodyLarge)
                Text(tr("Pictures for scrubbing, thumbnails and keyframe analysis of opened videos – kept in the " + "app's own storage (not visible in the Files app), so a video opens again at once. ") +
                    when {
                        bytes < 0 -> ""
                        bytes < 1_000_000 -> tr("Now: under 1 MB.")
                        else -> tr("Now: %d MB.", bytes / 1_000_000)
                    }, style = MaterialTheme.typography.bodySmall)
                OutlinedButton({ confirmDelete = true }, enabled = bytes > 0) { Text(tr("Delete previews")) }
            }
            Text(tr("Previews nobody needs (video not open, not in the batch list, no .cst) are deleted " + "automatically 2 minutes after the start, when the app is idle; together at most 2 GB."),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClose, Modifier.align(Alignment.End)) { Text(tr("Close")) }
        }
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text(tr("Delete all previews?")) },
            text = { Text(tr("Videos opened later build their previews again (a few seconds each). " + "Saved videos and Clip Speed Treatments are not touched.")) },
            confirmButton = {
                TextButton({
                    confirmDelete = false
                    vm.clearPreviews { n ->
                        vm.message = trp("Deleted the previews of %d video", "Deleted the previews of %d videos", n, n)
                        refresh++
                    }
                }) { Text(tr("Delete")) }
            },
            dismissButton = { TextButton({ confirmDelete = false }) { Text(tr("Keep")) } },
        )
    }
}

@Composable
private fun ModeChoice(name: String, info: String, selected: Boolean, onSelect: () -> Unit) {
    Surface(
        onClick = onSelect,
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(if (selected) 2.dp else 1.dp, if (selected) ChosenGreen else MaterialTheme.colorScheme.outline),
        color = if (selected) ChosenGreen.copy(alpha = 0.12f) else Color.Transparent,
    ) {
        Row(Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.Top) {
            RadioButton(selected, onSelect, colors = RadioButtonDefaults.colors(selectedColor = ChosenGreen))
            Column(Modifier.padding(start = 4.dp, top = 10.dp)) {
                Text(name, style = MaterialTheme.typography.titleSmall)
                Text(info, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun FolderRow(title: String, path: String, onOpen: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onOpen), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(path, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        TextButton(onOpen) { Text(tr("Open")) }
    }
}

/**
 * A language in its own name; Klingon also says what it is (user): "tlhIngan Hol (Klingonisch)"
 * in a German interface, "(Klingon)" in every other.
 */
private fun languageLabel(l: I18n.Language): String =
    if (l.code == "tlh") "${l.name} (${if (I18n.german) "Klingonisch" else "Klingon"})" else l.name
