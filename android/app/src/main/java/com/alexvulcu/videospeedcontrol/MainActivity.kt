package com.alexvulcu.videospeedcontrol

import android.Manifest
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Surface
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextOverflow
import android.content.Intent
import android.content.pm.PackageManager
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.alexvulcu.videospeedcontrol.ui.BatchCard
import com.alexvulcu.videospeedcontrol.ui.VideoGallery
import com.alexvulcu.videospeedcontrol.ui.AppMenu
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import com.alexvulcu.videospeedcontrol.ui.tr
import com.alexvulcu.videospeedcontrol.ui.GearIcon
import com.alexvulcu.videospeedcontrol.ui.I18n
import androidx.compose.foundation.clickable
import com.alexvulcu.videospeedcontrol.ui.TreatmentCard
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.viewModels
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.alexvulcu.videospeedcontrol.ui.ClipInfoCard
import com.alexvulcu.videospeedcontrol.ui.ClipState
import com.alexvulcu.videospeedcontrol.ui.EditorViewModel
import com.alexvulcu.videospeedcontrol.ui.ExportCard
import com.alexvulcu.videospeedcontrol.ui.PreviewPane
import com.alexvulcu.videospeedcontrol.ui.SectionsPanel
import com.alexvulcu.videospeedcontrol.ui.Timeline
import com.alexvulcu.videospeedcontrol.ui.TransportPanel
import com.alexvulcu.videospeedcontrol.ui.TrimPanel

class MainActivity : ComponentActivity() {
    private val vm: EditorViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        I18n.load(this)                     // English / German (menu behind the logo)
        enableEdgeToEdge()
        if (savedInstanceState == null) handle(intent)
        setContent {
            // right-to-left languages (Hebrew) mirror the layout; the timeline stays left-to-right
            CompositionLocalProvider(LocalLayoutDirection provides
                if (I18n.current.rtl) LayoutDirection.Rtl else LayoutDirection.Ltr) {
                VscTheme { MainScreen(vm) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    /** "Open with" (VIEW) and "Share" (SEND) from other apps. */
    private fun handle(intent: Intent) {
        val uri = when (intent.action) {
            Intent.ACTION_VIEW -> intent.data
            Intent.ACTION_SEND -> intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
            else -> null
        } ?: return
        // keep access after a restart (batch list) – only possible if the other app allows it
        if (intent.flags and Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION != 0) {
            runCatching { contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
        }
        vm.open(uri)
    }
}

@Composable
fun VscTheme(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val colors = if (isSystemInDarkTheme()) dynamicDarkColorScheme(context)
    else dynamicLightColorScheme(context)
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable
fun MainScreen(vm: EditorViewModel = viewModel()) {
    val ctx = LocalContext.current
    // Clips are chosen in the app's own gallery (VideoGallery: newest first, real names); the
    // system file picker is the way to Downloads / cloud ("Other files…"). Not the photo picker:
    // it hands out numbers instead of the file names (PXL_….mp4 – needed for output names).
    var showGallery by remember { mutableStateOf(false) }
    var showMenu by remember { mutableStateOf(false) }
    var showConvert by remember { mutableStateOf(false) }
    if (showMenu) AppMenu(vm, onConvert = { showMenu = false; showConvert = true }) { showMenu = false }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            showGallery = false
            runCatching {
                ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            vm.open(uri)
        }
    }
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(vm.message) {
        vm.message?.let { snackbar.showSnackbar(it, withDismissAction = true); vm.message = null }
    }
    // notifications (export progress) – asked once, on the first export (or conversion)
    var afterPermission by remember { mutableStateOf<(() -> Unit)?>(null) }
    val notifyPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        afterPermission?.invoke(); afterPermission = null
    }
    val withNotifications: (() -> Unit) -> Unit = { action ->
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            afterPermission = action
            notifyPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else action()
    }
    val onExport = { withNotifications { vm.startExport() } }
    val loadCst = rememberLauncherForActivityResult(OpenInTreatments()) { uri ->
        if (uri != null) scope.launch {
            val text = withContext(Dispatchers.IO) { ctx.contentResolver.openInputStream(uri)!!.use { it.readBytes().decodeToString() } }
            vm.loadTreatment(text, uri.lastPathSegment?.substringAfterLast('/') ?: "treatment")
        }
    }
    val shareCst: () -> Unit = {
        scope.launch {
            val text = vm.treatmentText() ?: return@launch
            val file = java.io.File(java.io.File(ctx.cacheDir, "share").apply { mkdirs() }, vm.treatmentFileName())
            withContext(Dispatchers.IO) { file.writeText(text) }
            val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", file)
            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("application/octet-stream")
                .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), tr("Share treatment")))
        }
    }
    // another clip replaces the one in the editor – offer to keep its edits in the batch list first
    var askKeep by remember { mutableStateOf(false) }
    val choose = {
        if (vm.hasUnsavedWork) askKeep = true else showGallery = true
    }
    if (askKeep) {
        val name = (vm.clip as? ClipState.Loaded)?.info?.name ?: tr("this clip")
        AlertDialog(
            onDismissRequest = { askKeep = false },
            title = { Text(tr("Keep the edits of %s?", name)) },
            text = { Text(tr("Its sections and trim are not in the batch list yet. The next clip replaces it in the editor.")) },
            confirmButton = {
                TextButton({ askKeep = false; vm.addToBatch(); showGallery = true }) { Text(tr("Add to batch")) }
            },
            dismissButton = {
                Row {
                    TextButton({ askKeep = false }) { Text(tr("Cancel")) }
                    TextButton({ askKeep = false; showGallery = true }) { Text(tr("Discard")) }
                }
            },
        )
    }
    if (showConvert) {
        androidx.activity.compose.BackHandler { showConvert = false }
        com.alexvulcu.videospeedcontrol.ui.ConvertScreen(onClose = { showConvert = false },
            onStart = { start -> withNotifications { start() } })
        return
    }
    if (showGallery) {
        Surface(Modifier.fillMaxSize().statusBarsPadding()) {
            VideoGallery(onPick = { showGallery = false; vm.open(it) },
                onOtherFiles = { pick.launch(arrayOf("video/*")) }, onClose = { showGallery = false })
        }
        return
    }
    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            // stays visible while the editor scrolls, so a further clip can be added at any time
            Surface(tonalElevation = 3.dp) {
                Row(
                    Modifier.fillMaxWidth().statusBarsPadding().padding(start = 12.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    // the logo opens the menu (Easy / Pro, folders, previews)
                    Image(painterResource(R.drawable.vsc_logo), tr("Menu"),
                        Modifier.size(36.dp).clickable { showMenu = true })
                    Text(tr("VideoSpeedControl"), style = MaterialTheme.typography.titleMedium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    // Easy / Pro badge: tap to switch
                    Surface(
                        onClick = { vm.chooseEasy(!vm.easy) },
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(6.dp),
                        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                        color = androidx.compose.ui.graphics.Color.Transparent,
                    ) {
                        Text(if (vm.easy) "Easy" else "Pro", style = MaterialTheme.typography.labelMedium,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
                    }
                    androidx.compose.foundation.layout.Spacer(Modifier.weight(0.01f))
                    if (vm.clip is ClipState.Loaded) OutlinedButton(onClick = choose) { Text(tr("＋ Clip")) }
                }
                    // settings at the right margin: the same menu as the logo (user request 2026-11-04;
                    // "Choose clip" moved to the start screen)
                    androidx.compose.material3.IconButton({ showMenu = true }) {
                        androidx.compose.material3.Icon(GearIcon, tr("Settings"), Modifier.size(28.dp))
                    }
                }
            }
        },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (val s = vm.clip) {
                ClipState.None -> {
                    Text(tr("Choose a clip – ideally a slow-motion recording."))
                    Button(onClick = choose) { Text(tr("Choose clip")) }
                    androidx.compose.material3.HorizontalDivider(Modifier.padding(vertical = 8.dp))
                    Text(tr("Video conversion (alpha)"), style = MaterialTheme.typography.titleMedium)
                    OutlinedButton({ showConvert = true }) { Text(tr("Convert videos (many at once) …")) }
                    BatchCard(vm, choose)
                }
                ClipState.Loading -> CircularProgressIndicator()
                is ClipState.Failed -> {
                    Text(s.message, color = MaterialTheme.colorScheme.error)
                    Button(onClick = choose) { Text(tr("Choose clip")) }
                }
                is ClipState.Loaded -> {
                    val edit = vm.edit ?: return@Column
                    vm.decodeNote?.let {
                        Text(it, style = MaterialTheme.typography.bodySmall,
                            color = if (vm.decodeSevere) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    PreviewPane(vm, s.info)
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Timeline(vm.shownEdit(edit), vm.playhead, vm.pendingStart, vm.selectedSection, vm.thumbs, vm.proxyProgress,
                            vm::seekFromTimeline, onTap = vm::tapTimeline, ramps = vm.rampZones(),
                            draggedBorder = vm.draggedBorder, onBorderDragStart = vm::beginBorderDrag,
                            onBorderDrag = vm::dragBorderTo, onBorderDragEnd = vm::endBorderDrag,
                            onTrimDrag = vm::dragTrim, easy = vm.easy)
                    }
                    TransportPanel(vm, edit)
                    SectionsPanel(vm, edit)
                    if (!vm.easy) TrimPanel(vm, edit)       // Easy: the yellow brackets on the timeline
                    ExportCard(vm, edit, onExport)
                    BatchCard(vm, choose)
                    TreatmentCard(vm, onSave = vm::saveTreatment,
                        onLoad = { loadCst.launch(arrayOf("*/*")) }, onShare = shareCst)
                    ClipInfoCard(s.info)
                }
            }
        }
    }
}

/** File picker for .cst files that starts in Documents/VideoSpeedControl/Clip Speed Treatments. */
class OpenInTreatments : ActivityResultContracts.OpenDocument() {
    override fun createIntent(context: android.content.Context, input: Array<String>): Intent =
        super.createIntent(context, input).putExtra(android.provider.DocumentsContract.EXTRA_INITIAL_URI,
            com.alexvulcu.videospeedcontrol.core.CstStore.folderUri)
}
