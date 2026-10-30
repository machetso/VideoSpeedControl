package com.alexvulcu.videospeedcontrol.export

import com.alexvulcu.videospeedcontrol.ui.tr
import com.alexvulcu.videospeedcontrol.ui.I18n
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.alexvulcu.videospeedcontrol.MainActivity
import com.alexvulcu.videospeedcontrol.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Foreground service that runs the export queue ([ExportManager]) with a progress notification,
 * so exports continue when the app is in the background. Stops itself when the queue is empty and
 * posts a summary notification.
 */
class ExportService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, tr("Exports"), NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel(CHANNEL_DONE, tr("Finished exports"), NotificationManager.IMPORTANCE_DEFAULT))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ExportManager.init(this)
        I18n.load(this)
        val type = if (ExportManager.mediaProcessingType) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING
        else ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        // directly, not via ServiceCompat: that started the service "with type none" on Android 17
        startForeground(ID, notification(tr("Preparing …"), 0f, true), type)
        if (!running) {
            running = true
            scope.launch {
                ExportManager.entries.collectLatest { list -> update(list) }
            }
            scope.launch(Dispatchers.IO) {
                val before = ExportManager.entries.value.filter { it.status == ExportManager.Status.DONE }.map { it.task.id }.toSet()
                // a task added just as the queue ran empty is picked up before stopping
                do { ExportManager.runQueue() } while (ExportManager.entries.value.any { it.status == ExportManager.Status.WAITING })
                finished(before)
            }
        }
        return START_NOT_STICKY
    }

    private fun update(list: List<ExportManager.Entry>) {
        val current = list.firstOrNull { it.status == ExportManager.Status.RUNNING } ?: return
        val queued = list.count { it.status == ExportManager.Status.WAITING }
        val name = current.task.treatment.sourceName
        val text = if (queued > 0) tr("%s – %d more waiting", name, queued) else name
        getSystemService(NotificationManager::class.java)
            .notify(ID, notification(text, current.progress, false))
    }

    private fun finished(doneBefore: Set<Long>) {
        val list = ExportManager.entries.value
        val done = list.filter { it.status == ExportManager.Status.DONE && it.task.id !in doneBefore }
        val failed = list.count { it.status == ExportManager.Status.FAILED }
        val nm = getSystemService(NotificationManager::class.java)
        val text = buildString {
            append(if (done.size == 1) tr("Saved %s in Movies/VideoSpeedControl", done[0].output)
                else tr("%d files saved in Movies/VideoSpeedControl", done.size))
            if (failed > 0) append(tr(" · %d failed", failed))
        }
        nm.notify(ID_DONE, NotificationCompat.Builder(this, CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_stat_export)
            .setContentTitle(tr("Video saved"))
            .setContentText(text)
            .setContentIntent(openApp())
            .setAutoCancel(true)
            .build())
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        running = false
        stopSelf()
    }

    private fun notification(text: String, progress: Float, indeterminate: Boolean) =
        NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_export)
            .setContentTitle(tr("Still saving – the video appears when it is finished"))
            .setContentText(text)
            .setProgress(1000, (progress * 1000).toInt(), indeterminate)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openApp())
            .build()

    private fun openApp(): PendingIntent = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL = "exports"
        private const val CHANNEL_DONE = "exports_done"
        private const val ID = 1
        private const val ID_DONE = 2
    }
}
