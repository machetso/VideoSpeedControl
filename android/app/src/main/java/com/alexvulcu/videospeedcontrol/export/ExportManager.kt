package com.alexvulcu.videospeedcontrol.export

import android.content.Context
import android.net.Uri
import android.os.Build
import androidx.core.content.ContextCompat
import com.alexvulcu.videospeedcontrol.core.ExportCancelled
import com.alexvulcu.videospeedcontrol.core.ExportTask
import com.alexvulcu.videospeedcontrol.core.Exporter
import com.alexvulcu.videospeedcontrol.core.OutputStore
import com.alexvulcu.videospeedcontrol.core.Treatment
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * App-wide export queue. Single exports and batch entries are [ExportTask]s; waiting ones are run
 * one after another by [ExportService] (a foreground service, so exports go on when the app is in
 * the background). Batch entries are stored in files/batch.json and survive a restart; an entry
 * exported successfully is marked done and skipped by later batch exports (desktop behaviour).
 */
object ExportManager {
    enum class Status { IDLE, WAITING, RUNNING, DONE, FAILED, CANCELLED }

    data class Entry(
        val task: ExportTask,
        val inBatch: Boolean,
        val status: Status = Status.IDLE,
        val progress: Float = 0f,
        val output: String? = null,          // display name of the file written
        val outputUri: Uri? = null,
        val error: String? = null,
        val seconds: Double = 0.0,
        val frames: Int = 0,
    )

    private val _entries = MutableStateFlow<List<Entry>>(emptyList())
    val entries: StateFlow<List<Entry>> = _entries.asStateFlow()
    private var app: Context? = null
    private var nextId = 1L
    @Volatile private var cancelCurrent: (() -> Unit)? = null

    fun init(context: Context) {
        if (app != null) return
        app = context.applicationContext
        load()
    }

    val batch: List<Entry> get() = _entries.value.filter { it.inBatch }

    fun newId(): Long = synchronized(this) { nextId++ }

    // ------------------------------------------------------------------ editing the list

    fun addToBatch(task: ExportTask) {
        _entries.update { it + Entry(task, inBatch = true) }
        save()
    }

    /** Replace a batch entry's task (edited in the editor); it is no longer done. */
    fun updateBatchEntry(id: Long, task: ExportTask) {
        _entries.update { list -> list.map { if (it.task.id == id) Entry(task.copy(id = id), true) else it } }
        save()
    }

    fun remove(id: Long) {
        if (_entries.value.any { it.task.id == id && it.status == Status.RUNNING }) cancel(id)
        _entries.update { list -> list.filterNot { it.task.id == id && it.status != Status.RUNNING } }
        save()
    }

    fun clearDone() {
        _entries.update { list -> list.filterNot { it.inBatch && it.status == Status.DONE } }
        save()
    }

    // ------------------------------------------------------------------ running

    /** Export one task now (not part of the batch list). */
    fun exportNow(task: ExportTask) {
        _entries.update { list -> list.filterNot { !it.inBatch && it.status != Status.RUNNING && it.status != Status.WAITING } +
            Entry(task, inBatch = false, status = Status.WAITING) }
        startService()
    }

    /** Queue every batch entry that is not done yet. */
    fun exportBatch() {
        _entries.update { list ->
            list.map {
                if (it.inBatch && it.status in setOf(Status.IDLE, Status.FAILED, Status.CANCELLED))
                    it.copy(status = Status.WAITING, progress = 0f, error = null) else it
            }
        }
        save()
        startService()
    }

    fun cancel(id: Long) {
        val e = _entries.value.firstOrNull { it.task.id == id } ?: return
        when (e.status) {
            Status.RUNNING -> cancelCurrent?.invoke()
            Status.WAITING -> set(id) { it.copy(status = Status.CANCELLED) }
            else -> {}
        }
    }

    fun cancelAll() {
        _entries.update { list -> list.map { if (it.status == Status.WAITING) it.copy(status = Status.CANCELLED) else it } }
        cancelCurrent?.invoke()
        save()
    }

    val hasWork: Boolean get() = _entries.value.any { it.status == Status.WAITING || it.status == Status.RUNNING }

    private fun startService() {
        val ctx = app ?: return
        val intent = android.content.Intent(ctx, ExportService::class.java)
        ContextCompat.startForegroundService(ctx, intent)
    }

    /** Run waiting tasks until none is left (called by the service on a background thread). */
    fun runQueue() {
        val ctx = app ?: return
        while (true) {
            val e = _entries.value.firstOrNull { it.status == Status.WAITING } ?: return
            runOne(ctx, e)
        }
    }

    private fun runOne(ctx: Context, e: Entry) {
        val id = e.task.id
        set(id) { it.copy(status = Status.RUNNING, progress = 0f, error = null) }
        val store = OutputStore(ctx)
        var out: OutputStore.Output? = null
        val t0 = System.nanoTime()
        try {
            val running = Exporter.prepare(ctx, e.task)
            cancelCurrent = running.cancel
            if (_entries.value.firstOrNull { it.task.id == id }?.status != Status.RUNNING) throw ExportCancelled()
            val o = store.create(running.stem, running.extension, running.mime)
            out = o
            var last = 0L
            val frames = store.open(o).use { pfd ->
                running.run(pfd.fileDescriptor) { p ->
                    val now = System.nanoTime()
                    if (now - last > 100_000_000L) { last = now; set(id) { it.copy(progress = p) } }
                }
            }
            store.publish(o)
            set(id) { it.copy(status = Status.DONE, progress = 1f, output = o.displayName, outputUri = o.uri,
                frames = frames, seconds = (System.nanoTime() - t0) / 1e9) }
        } catch (ex: Throwable) {
            out?.let { store.discard(it) }
            if (ex is ExportCancelled) set(id) { it.copy(status = Status.CANCELLED) }
            else set(id) { it.copy(status = Status.FAILED, error = ex.message ?: ex.toString()) }
        } finally {
            cancelCurrent = null
            save()
        }
    }

    private fun set(id: Long, change: (Entry) -> Entry) {
        _entries.update { list -> list.map { if (it.task.id == id) change(it) else it } }
    }

    // ------------------------------------------------------------------ persistence (batch only)

    private fun file(): File? = app?.let { File(it.filesDir, "batch.json") }

    @Synchronized
    private fun save() {
        val f = file() ?: return
        val arr = JSONArray()
        for (e in batch) {
            arr.put(JSONObject().apply {
                put("id", e.task.id)
                put("uri", e.task.uri.toString())
                put("mime", e.task.sourceMime)
                // a running / waiting entry is not done – after a restart it is simply open again
                put("status", if (e.status == Status.DONE) "done" else "open")
                put("output", e.output ?: JSONObject.NULL)
                put("output_uri", e.outputUri?.toString() ?: JSONObject.NULL)
                put("treatment", Treatment.toJson(e.task.treatment, e.task.sourceMime))
            })
        }
        val tmp = File(f.path + ".tmp")
        tmp.writeText(arr.toString(1))
        tmp.renameTo(f)
    }

    private fun load() {
        val f = file() ?: return
        if (!f.isFile) return
        val list = runCatching {
            val arr = JSONArray(f.readText())
            (0 until arr.length()).mapNotNull { i ->
                val o = arr.getJSONObject(i)
                runCatching {
                    val task = ExportTask(o.getLong("id"), Uri.parse(o.getString("uri")),
                        Treatment.fromJson(o.getString("treatment"), "batch entry"), o.getString("mime"))
                    val done = o.optString("status") == "done"
                    Entry(task, inBatch = true, status = if (done) Status.DONE else Status.IDLE,
                        output = if (o.isNull("output")) null else o.getString("output"),
                        outputUri = if (o.isNull("output_uri")) null else Uri.parse(o.getString("output_uri")))
                }.getOrNull()
            }
        }.getOrDefault(emptyList())
        nextId = (list.maxOfOrNull { it.task.id } ?: 0L) + 1
        _entries.value = list
    }

    /** Used by Build checks in the service. */
    val mediaProcessingType: Boolean get() = Build.VERSION.SDK_INT >= 35
}
