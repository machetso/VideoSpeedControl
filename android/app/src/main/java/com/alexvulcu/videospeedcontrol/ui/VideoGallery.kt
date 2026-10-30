package com.alexvulcu.videospeedcontrol.ui

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.text.format.DateFormat
import android.util.LruCache
import android.util.Size
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.runtime.DisposableEffect
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.Date

/**
 * In-app video picker: the phone's videos newest first (camera folder by default), with real
 * file names (the system photo picker only hands out numbers) and lasting access (needed by the
 * batch list after a restart). Downloads / cloud files: "Other files…" (system file picker).
 */
object Gallery {
    data class Video(val uri: Uri, val name: String, val durationMs: Long, val taken: Long, val camera: Boolean)

    enum class Access { FULL, PARTIAL, NONE }

    val permissions: Array<String>
        get() = when {
            Build.VERSION.SDK_INT >= 34 ->
                arrayOf(Manifest.permission.READ_MEDIA_VIDEO, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
            Build.VERSION.SDK_INT >= 33 -> arrayOf(Manifest.permission.READ_MEDIA_VIDEO)
            else -> arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        }

    fun access(context: Context): Access {
        fun granted(p: String) = context.checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED
        return when {
            Build.VERSION.SDK_INT >= 33 && granted(Manifest.permission.READ_MEDIA_VIDEO) -> Access.FULL
            Build.VERSION.SDK_INT < 33 && granted(Manifest.permission.READ_EXTERNAL_STORAGE) -> Access.FULL
            Build.VERSION.SDK_INT >= 34 && granted(Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) -> Access.PARTIAL
            else -> Access.NONE
        }
    }

    fun load(context: Context): List<Video> {
        val collection = MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
        val projection = arrayOf(MediaStore.Video.Media._ID, MediaStore.Video.Media.DISPLAY_NAME,
            MediaStore.Video.Media.DURATION, MediaStore.Video.Media.DATE_TAKEN, MediaStore.Video.Media.DATE_ADDED,
            MediaStore.Video.Media.RELATIVE_PATH)
        val out = ArrayList<Video>()
        context.contentResolver.query(collection, projection, null, null, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val taken = if (c.isNull(3)) c.getLong(4) * 1000 else c.getLong(3)
                val path = c.getString(5) ?: ""
                out += Video(ContentUris.withAppendedId(collection, id), c.getString(1) ?: "$id",
                    c.getLong(2), taken, path.startsWith("DCIM/Camera", ignoreCase = true))
            }
        }
        // newest first; files without a recording date (downloads, messengers): when they arrived
        return out.sortedByDescending { it.taken }
    }

    private val thumbs = LruCache<Uri, Bitmap>(120)

    suspend fun thumbnail(context: Context, uri: Uri): Bitmap? = thumbs.get(uri) ?: withContext(Dispatchers.IO) {
        runCatching { context.contentResolver.loadThumbnail(uri, Size(320, 320), null) }.getOrNull()
    }?.also { thumbs.put(uri, it) }
}

@Composable
fun VideoGallery(onPick: (Uri) -> Unit, onOtherFiles: () -> Unit, onClose: () -> Unit) {
    val ctx = LocalContext.current
    BackHandler(onBack = onClose)
    var access by remember { mutableStateOf(Gallery.access(ctx)) }
    var asked by remember { mutableStateOf(false) }
    var reload by remember { mutableStateOf(0) }
    val request = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        access = Gallery.access(ctx)
        asked = true
        reload++                      // "Select more" keeps PARTIAL access but changes the list
    }
    // ask right away the first time; afterwards the screen explains and offers the button
    LaunchedEffect(Unit) { if (access == Gallery.Access.NONE) request.launch(Gallery.permissions) }
    // the permission may change in the system settings while the app is in the background
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, e -> if (e == Lifecycle.Event.ON_RESUME) access = Gallery.access(ctx) }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    var cameraOnly by remember { mutableStateOf(true) }
    val videos by produceState<List<Gallery.Video>?>(null, access, reload) {
        value = if (access == Gallery.Access.NONE) emptyList() else withContext(Dispatchers.IO) { Gallery.load(ctx) }
    }
    val shown = videos?.let { list -> if (cameraOnly && access == Gallery.Access.FULL) list.filter { it.camera } else list }

    Column(Modifier.fillMaxSize()) {
        Surface(tonalElevation = 3.dp) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClose) { Text(tr("← Back")) }
                    Text(tr("Choose a clip"), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                    OutlinedButton(onOtherFiles) { Text(tr("Other files…")) }
                }
                if (access == Gallery.Access.FULL) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(cameraOnly, { cameraOnly = true }, label = { Text(tr("Camera")) })
                        FilterChip(!cameraOnly, { cameraOnly = false }, label = { Text(tr("All videos")) })
                    }
                }
            }
        }
        when {
            access == Gallery.Access.NONE -> Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(tr("To list your recordings (newest first, with their real file names), VideoSpeedControl " + "needs access to your videos. It only reads them – the originals are never changed."))
                if (asked) Text(tr("Access was not given. You can still open a clip with “Other files…”, or allow " + "access in the system settings (Apps › VideoSpeedControl › Permissions)."),
                    style = MaterialTheme.typography.bodySmall)
                Button({ request.launch(Gallery.permissions) }) { Text(tr("Allow access to videos")) }
            }
            shown == null -> Text(tr("Loading …"), Modifier.padding(16.dp))
            else -> {
                if (access == Gallery.Access.PARTIAL) {
                    Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(tr("Only the videos you selected are shown."), style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f))
                        TextButton({ request.launch(Gallery.permissions) }) { Text(tr("Select more")) }
                    }
                }
                if (shown.isEmpty()) Text(if (cameraOnly && access == Gallery.Access.FULL) tr("No videos in the camera folder.")
                    else tr("No videos found."), Modifier.padding(16.dp))
                LazyVerticalGrid(GridCells.Adaptive(110.dp), Modifier.fillMaxSize().padding(4.dp)) {
                    items(shown, key = { it.uri.toString() }) { v -> VideoTile(v) { onPick(v.uri) } }
                }
            }
        }
    }
}

@Composable
private fun VideoTile(v: Gallery.Video, onClick: () -> Unit) {
    val ctx = LocalContext.current
    val thumb by produceState<Bitmap?>(null, v.uri) { value = Gallery.thumbnail(ctx, v.uri) }
    Column(Modifier.padding(4.dp).clickable(onClick = onClick)) {
        Box(Modifier.fillMaxWidth().aspectRatio(1f).background(MaterialTheme.colorScheme.surfaceVariant)) {
            thumb?.let { Image(it.asImageBitmap(), v.name, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
            Text(duration(v.durationMs), Modifier.align(Alignment.BottomEnd).background(Color(0x99000000))
                .padding(horizontal = 4.dp), color = Color.White, style = MaterialTheme.typography.labelSmall)
        }
        val date = Date(v.taken)
        Text(DateFormat.getMediumDateFormat(ctx).format(date) + " " + DateFormat.getTimeFormat(ctx).format(date),
            style = MaterialTheme.typography.labelSmall, maxLines = 1)
        Text(v.name, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

private fun duration(ms: Long): String {
    val s = (ms + 500) / 1000
    return if (s >= 3600) "%d:%02d:%02d".format(s / 3600, s / 60 % 60, s % 60) else "%d:%02d".format(s / 60, s % 60)
}
