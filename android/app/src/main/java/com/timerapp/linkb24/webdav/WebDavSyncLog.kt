package com.timerapp.linkb24.webdav

import android.content.Context
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

@Serializable
data class SyncLogEntry(
    val ts: String,
    val op: String,
    @SerialName("uploaded_tasks") val uploadedTasks: Int = 0,
    @SerialName("downloaded_tasks") val downloadedTasks: Int = 0,
    val ok: Boolean = true,
    val error: String = "",
) {
    fun displayLine(): String {
        val status = if (ok) "OK" else "ОШИБКА: $error"
        return "$ts  ${op.padEnd(16)}  ↑$uploadedTasks  ↓$downloadedTasks  $status"
    }
}

class WebDavSyncLog(
    private val logFile: File,
) {
    constructor(context: Context) : this(File(context.filesDir, LOG_FILENAME))

    fun append(
        op: String,
        uploadedTasks: Int = 0,
        downloadedTasks: Int = 0,
        ok: Boolean = true,
        error: String = "",
    ): SyncLogEntry {
        val entry = SyncLogEntry(
            ts = LocalDateTime.now().format(TS_FORMAT),
            op = op,
            uploadedTasks = uploadedTasks.coerceAtLeast(0),
            downloadedTasks = downloadedTasks.coerceAtLeast(0),
            ok = ok,
            error = if (ok) "" else error.trim(),
        )
        val entries = readEntries().toMutableList()
        entries.add(entry)
        val trimmed = if (entries.size > MAX_ENTRIES) {
            entries.takeLast(MAX_ENTRIES)
        } else {
            entries
        }
        logFile.parentFile?.mkdirs()
        logFile.writeText(
            trimmed.joinToString("\n") { LOG_JSON.encodeToString(SyncLogEntry.serializer(), it) } +
                if (trimmed.isEmpty()) "" else "\n",
        )
        return entry
    }

    fun readEntries(): List<SyncLogEntry> {
        if (!logFile.isFile) {
            return emptyList()
        }
        return logFile.readLines()
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .mapNotNull { line ->
                runCatching {
                    LOG_JSON.decodeFromString(SyncLogEntry.serializer(), line)
                }.getOrNull()
            }
    }

    fun formatForDisplay(): String {
        val entries = readEntries()
        if (entries.isEmpty()) {
            return "Журнал пуст."
        }
        return entries.joinToString("\n") { it.displayLine() }
    }

    fun clear() {
        if (logFile.isFile) {
            logFile.delete()
        }
    }

    companion object {
        const val LOG_FILENAME = "webdav-sync.log"
        const val MAX_ENTRIES = 200
        private val TS_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
        private val LOG_JSON = Json { ignoreUnknownKeys = true }

        fun countTasksInPayload(payload: ByteArray?): Int {
            if (payload == null || payload.isEmpty()) {
                return 0
            }
            return runCatching {
                val element = LOG_JSON.parseToJsonElement(payload.toString(Charsets.UTF_8))
                val root = element as? JsonObject ?: return 0
                val tasks = root["tasks"] as? JsonArray ?: return 0
                tasks.size
            }.getOrDefault(0)
        }
    }
}
