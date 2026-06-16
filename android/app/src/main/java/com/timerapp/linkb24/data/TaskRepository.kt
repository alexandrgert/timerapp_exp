package com.timerapp.linkb24.data

import android.content.Context
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

private val zoneId: ZoneId = ZoneId.systemDefault()

fun parseInstant(value: String): Instant {
    return runCatching { Instant.parse(value) }.getOrElse {
        runCatching {
            OffsetDateTime.parse(value, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant()
        }.getOrElse {
            LocalDateTime.parse(value, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                .atZone(zoneId)
                .toInstant()
        }
    }
}

class TaskRepository(context: Context) {
    private val dataFile = File(context.filesDir, "data.json")

    fun load(): AppDataDto {
        if (!dataFile.isFile) {
            return AppDataDto()
        }
        return runCatching {
            AppJson.decodeFromString(AppDataDto.serializer(), dataFile.readText())
        }.getOrDefault(AppDataDto())
    }

    fun save(data: AppDataDto) {
        dataFile.parentFile?.mkdirs()
        dataFile.writeText(AppJson.encodeToString(AppDataDto.serializer(), data))
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

    fun completeTask(taskId: String, data: AppDataDto): AppDataDto {
        val now = OffsetDateTime.now(zoneId).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val tasks = data.tasks.map { task ->
            if (task.id != taskId) {
                task
            } else {
                val paused = pauseRunningTask(task)
                paused.copy(status = TaskStatus.COMPLETED, completedAt = now)
            }
        }
        return data.copy(tasks = tasks)
    }

    fun deleteTask(taskId: String, data: AppDataDto): AppDataDto {
        return data.copy(tasks = data.tasks.filterNot { it.id == taskId })
    }

    private fun startTask(task: TaskDto): TaskDto {
        val now = OffsetDateTime.now(zoneId).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val session = SessionDto(
            id = UUID.randomUUID().toString().replace("-", ""),
            startedAt = now,
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
        val start = parseInstant(session.startedAt)
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
