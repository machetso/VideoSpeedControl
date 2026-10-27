package com.alexvulcu.videospeedcontrol

import android.content.Intent
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
        enableEdgeToEdge()
        if (savedInstanceState == null) handle(intent)
        setContent { VscTheme { MainScreen(vm) } }
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
    // System file picker rather than the photo picker: it passes on the real file name
    // (PXL_….mp4 – needed for output names and .cst files) and also reaches Downloads / cloud.
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            runCatching {
                ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            vm.open(uri)
        }
    }
    Scaffold { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("VideoSpeedControl", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                val choose = { pick.launch(arrayOf("video/*")) }
                if (vm.clip is ClipState.Loaded) OutlinedButton(onClick = choose) { Text("Other clip") }
                else Button(onClick = choose) { Text("Choose clip") }
            }
            when (val s = vm.clip) {
                ClipState.None -> Text("Choose a clip – ideally a slow-motion recording.")
                ClipState.Loading -> CircularProgressIndicator()
                is ClipState.Failed -> Text(s.message, color = MaterialTheme.colorScheme.error)
                is ClipState.Loaded -> {
                    val edit = vm.edit ?: return@Column
                    PreviewPane(vm, s.info)
                    Timeline(edit, vm.playhead, vm.pendingStart, vm.selectedSection, vm.thumbs, vm.proxyProgress, vm::seekFromTimeline)
                    TransportPanel(vm, edit)
                    SectionsPanel(vm, edit)
                    TrimPanel(vm, edit)
                    ExportCard(vm, edit)
                    ClipInfoCard(s.info)
                }
            }
        }
    }
}
