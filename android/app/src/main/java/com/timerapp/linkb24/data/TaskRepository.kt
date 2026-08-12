package com.timerapp.linkb24.data

import android.content.Context
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

private val zoneId: ZoneId = ZoneId.systemDefault()

fun parseInstant(value: String): Instant? {
    if (value.isBlank()) {
        return null
    }
    return runCatching { Instant.parse(value) }.getOrElse {
        runCatching {
            OffsetDateTime.parse(value, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant()
        }.getOrElse {
            runCatching {
                LocalDateTime.parse(value, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                    .atZone(zoneId)
                    .toInstant()
            }.getOrNull()
        }
    }
}

class TaskRepository(
    val dataFile: File,
) {
    constructor(context: Context) : this(File(context.filesDir, "data.json"))

    private val backupFile: File
        get() = File(dataFile.parentFile, "${dataFile.name}.bak")

    fun load(): AppDataDto {
        val raw = loadFromFile(dataFile) ?: loadFromFile(backupFile) ?: AppDataDto()
        val prepared = prepareLoadedData(raw)
        if (prepared != raw) {
            save(prepared)
        }
        return prepared
    }

    companion object {
        fun prepareLoadedData(data: AppDataDto): AppDataDto {
            val normalized = normalizeRunningTasks(data)
            return ensurePlanRollover(normalized).data
        }
    }

    private fun loadFromFile(file: File): AppDataDto? {
        if (!file.isFile) {
            return null
        }
        return runCatching {
            AppJson.decodeFromString(AppDataDto.serializer(), file.readText())
        }.getOrNull()
    }

    fun save(data: AppDataDto) {
        dataFile.parentFile?.mkdirs()
        val payload = AppJson.encodeToString(AppDataDto.serializer(), data)
        val tempFile = File(dataFile.parentFile, "${dataFile.name}.tmp")
        tempFile.writeText(payload)
        if (dataFile.isFile) {
            dataFile.copyTo(backupFile, overwrite = true)
        }
        Files.move(
            tempFile.toPath(),
            dataFile.toPath(),
            StandardCopyOption.REPLACE_EXISTING,
            StandardCopyOption.ATOMIC_MOVE,
        )
    }

    fun createTask(title: String, data: AppDataDto): AppDataDto {
        val trimmed = title.trim()
        require(trimmed.isNotEmpty()) { "Title required" }
        val today = LocalDate.now(zoneId).format(DateTimeFormatter.ISO_LOCAL_DATE)
        val now = OffsetDateTime.now(zoneId).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val task = TaskDto(
            id = UUID.randomUUID().toString().replace("-", ""),
            day = today,
            title = trimmed,
            createdAt = now,
            plannedDays = listOf(today),
        )
        return data.copy(tasks = data.tasks + task)
    }

    fun toggleTimer(taskId: String, data: AppDataDto): AppDataDto {
        val tasks = data.tasks.map { task ->
            if (task.id != taskId) {
                pauseRunningTask(task)
            } else {
                when (task.status) {
                    TaskStatus.RUNNING -> pauseRunningTask(task)
                    else -> startTask(task)
                }
            }
        }
        return data.copy(tasks = tasks)
    }

    fun completeTask(taskId: String, data: AppDataDto, result: String): AppDataDto {
        val trimmed = result.trim()
        require(trimmed.isNotEmpty()) { "Введите результат выполнения задачи." }
        val now = OffsetDateTime.now(zoneId).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val tasks = data.tasks.map { task ->
            if (task.id != taskId) {
                task
            } else {
                val paused = pauseRunningTask(task)
                paused.copy(
                    status = TaskStatus.COMPLETED,
                    completedAt = now,
                    result = trimmed,
                )
            }
        }
        return data.copy(tasks = tasks)
    }

    fun resumeCompletedTask(taskId: String, data: AppDataDto, comment: String = ""): AppDataDto {
        val pausedOthers = data.copy(tasks = data.tasks.map { pauseRunningTask(it) })
        val tasks = pausedOthers.tasks.map { task ->
            if (task.id != taskId) {
                task
            } else {
                val reopened = task.copy(status = TaskStatus.OPEN, completedAt = null)
                startTask(reopened, comment = comment)
            }
        }
        return data.copy(tasks = tasks)
    }

    fun updateTask(
        taskId: String,
        data: AppDataDto,
        title: String? = null,
        description: String? = null,
        result: String? = null,
        keepPriority: Boolean? = null,
    ): AppDataDto {
        val tasks = data.tasks.map { task ->
            if (task.id != taskId) {
                task
            } else {
                var updated = task
                if (title != null) {
                    val trimmed = title.trim()
                    require(trimmed.isNotEmpty()) { "Название задачи не может быть пустым." }
                    updated = updated.copy(title = trimmed)
                }
                if (description != null) {
                    updated = updated.copy(description = description.trim())
                }
                if (result != null) {
                    val trimmedResult = result.trim()
                    if (task.status == TaskStatus.COMPLETED && trimmedResult.isEmpty()) {
                        throw IllegalArgumentException("Введите результат выполнения задачи.")
                    }
                    updated = updated.copy(result = trimmedResult)
                }
                if (keepPriority != null) {
                    updated = updated.copy(keepPriority = keepPriority)
                }
                updated
            }
        }
        return data.copy(tasks = tasks)
    }

    fun setKeepPriority(taskId: String, data: AppDataDto, keep: Boolean): AppDataDto {
        val tasks = data.tasks.map { task ->
            if (task.id != taskId) task else task.copy(keepPriority = keep)
        }
        return data.copy(tasks = tasks)
    }

    fun assignTaskPriority(taskId: String, data: AppDataDto, priority: Int, dateIso: String = todayIsoDate()): AppDataDto {
        val tasks = data.tasks.map { task ->
            if (task.id != taskId) task else withTaskPriority(task, dateIso, priority)
        }
        return data.copy(tasks = tasks)
    }

    fun addClosedSession(
        taskId: String,
        data: AppDataDto,
        startedAt: String,
        endedAt: String,
        comment: String = "",
    ): AppDataDto {
        val start = parseInstant(startedAt) ?: throw IllegalArgumentException("Некорректное начало.")
        val end = parseInstant(endedAt) ?: throw IllegalArgumentException("Некорректное окончание.")
        require(end.isAfter(start)) { "Окончание должно быть позже начала." }
        val tasks = data.tasks.map { task ->
            if (task.id != taskId) {
                task
            } else {
                val session = SessionDto(
                    id = UUID.randomUUID().toString().replace("-", ""),
                    startedAt = startedAt,
                    endedAt = endedAt,
                    comment = comment.trim(),
                )
                val sessions = (task.sessions + session).sortedBy { it.startedAt }
                val status = when {
                    task.status == TaskStatus.COMPLETED -> task.status
                    sessions.any { it.endedAt == null } -> TaskStatus.RUNNING
                    sessions.isNotEmpty() -> TaskStatus.PAUSED
                    else -> task.status
                }
                task.copy(sessions = sessions, status = status)
            }
        }
        return data.copy(tasks = tasks)
    }

    fun setPriorityFilter(data: AppDataDto, levels: Set<Int>): AppDataDto {
        return data.copy(ui = withPriorityFilter(data.ui, levels))
    }

    fun deleteTask(taskId: String, data: AppDataDto): AppDataDto {
        return data.copy(tasks = data.tasks.filterNot { it.id == taskId })
    }

    private fun startTask(task: TaskDto, comment: String = ""): TaskDto {
        if (task.sessions.any { it.endedAt == null }) {
            return task.copy(status = TaskStatus.RUNNING)
        }
        val now = OffsetDateTime.now(zoneId).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val session = SessionDto(
            id = UUID.randomUUID().toString().replace("-", ""),
            startedAt = now,
            comment = comment.trim(),
        )
        return task.copy(status = TaskStatus.RUNNING, sessions = task.sessions + session)
    }

    private fun pauseRunningTask(task: TaskDto): TaskDto {
        val active = task.sessions.lastOrNull { it.endedAt == null } ?: return task
        if (task.status != TaskStatus.RUNNING) {
            return task
        }
        val now = OffsetDateTime.now(zoneId).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val sessions = task.sessions.map { session ->
            if (session.id == active.id) session.copy(endedAt = now) else session
        }
        return task.copy(status = TaskStatus.PAUSED, sessions = sessions)
    }
}

fun taskDurationSeconds(task: TaskDto, nowMillis: Long = System.currentTimeMillis()): Long {
    val nowInstant = Instant.ofEpochMilli(nowMillis)
    return task.sessions.sumOf { session ->
        val start = parseInstant(session.startedAt) ?: return@sumOf 0L
        val end = session.endedAt?.let(::parseInstant) ?: nowInstant
        (end.epochSecond - start.epochSecond).coerceAtLeast(0)
    }
}

fun formatDuration(totalSeconds: Long): String {
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    return if (hours > 0) {
        String.format("%d:%02d:%02d", hours, minutes, seconds)
    } else {
        String.format("%02d:%02d", minutes, seconds)
    }
}

fun isActive(task: TaskDto): Boolean {
    return task.status == TaskStatus.RUNNING || task.sessions.any { it.endedAt == null }
}
