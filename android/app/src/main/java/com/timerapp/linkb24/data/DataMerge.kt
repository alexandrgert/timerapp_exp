package com.timerapp.linkb24.data

import java.io.File

fun mergeAppData(states: List<AppDataDto>): AppDataDto {
    if (states.isEmpty()) {
        return AppDataDto()
    }
    val ranked = states.sortedWith(
        compareByDescending<AppDataDto> { it.tasks.size }
            .thenByDescending { state -> state.tasks.sumOf { task -> task.sessions.size } },
    )
    val mergedUi = ranked.first().ui
    val tasksById = linkedMapOf<String, TaskDto>()
    for (state in states) {
        for (task in state.tasks) {
            val existing = tasksById[task.id]
            tasksById[task.id] = when {
                existing == null -> task
                else -> mergeTaskPair(existing, task)
            }
        }
    }
    return AppDataDto(tasks = tasksById.values.toList(), ui = mergedUi)
}

fun mergeTaskPair(left: TaskDto, right: TaskDto): TaskDto {
    require(left.id == right.id) { "Task id mismatch" }
    val sessionsById = linkedMapOf<String, SessionDto>()
    for (session in left.sessions + right.sessions) {
        val existing = sessionsById[session.id]
        sessionsById[session.id] = when {
            existing == null -> session
            else -> pickRicherSession(existing, session)
        }
    }
    val mergedSessions = sessionsById.values.sortedBy { it.startedAt }
    val base = if (taskRicher(right, left)) right else left
    val other = if (base === right) left else right
    val plannedDays = (base.plannedDays + other.plannedDays).distinct()
    val description = base.description.ifBlank { other.description }
    val result = base.result.ifBlank { other.result }
    val dailyPriorities = mergeDailyPriorities(base.dailyPriorities, other.dailyPriorities)
    val (status, completedAt) = resolveMergedStatus(left, right, mergedSessions)
    return base.copy(
        sessions = mergedSessions,
        plannedDays = plannedDays,
        description = description,
        result = result,
        dailyPriorities = dailyPriorities,
        status = status,
        completedAt = completedAt,
    )
}

private fun resolveMergedStatus(
    left: TaskDto,
    right: TaskDto,
    sessions: List<SessionDto>,
): Pair<TaskStatus, String?> {
    if (sessions.any { it.endedAt == null }) {
        return TaskStatus.RUNNING to null
    }
    if (left.status == TaskStatus.COMPLETED || right.status == TaskStatus.COMPLETED) {
        val completedAt = listOfNotNull(left.completedAt, right.completedAt)
            .maxByOrNull { value -> parseInstant(value)?.toEpochMilli() ?: Long.MIN_VALUE }
        return TaskStatus.COMPLETED to completedAt
    }
    if (sessions.isNotEmpty()) {
        return TaskStatus.PAUSED to null
    }
    val base = if (taskRicher(right, left)) right else left
    return base.status to null
}

fun mergeDataFiles(localFile: File, remotePayload: ByteArray): AppDataDto {
    val remoteText = remotePayload.decodeToString()
    runCatching {
        AppJson.decodeFromString(AppDataDto.serializer(), remoteText)
    }.getOrElse {
        throw IllegalArgumentException("Удалённый файл не является корректным JSON")
    }
    val local = if (localFile.isFile) {
        AppJson.decodeFromString(AppDataDto.serializer(), localFile.readText())
    } else {
        AppDataDto()
    }
    val remote = AppJson.decodeFromString(AppDataDto.serializer(), remoteText)
    return mergeAppData(listOf(local, remote))
}

fun scoreDataFile(file: File): Triple<Int, Long, Long> {
    if (!file.isFile) {
        return Triple(0, 0L, 0L)
    }
    val loaded = runCatching {
        AppJson.decodeFromString(AppDataDto.serializer(), file.readText())
    }.getOrNull()
    val taskCount = loaded?.tasks?.size ?: 0
    return Triple(taskCount, file.length(), file.lastModified())
}

private fun pickRicherSession(existing: SessionDto, candidate: SessionDto): SessionDto {
    if (existing.endedAt != null && candidate.endedAt == null) {
        return existing
    }
    if (candidate.endedAt != null && existing.endedAt == null) {
        return candidate
    }
    val existingSeconds = sessionDurationSeconds(existing)
    val candidateSeconds = sessionDurationSeconds(candidate)
    if (candidateSeconds != existingSeconds) {
        return if (candidateSeconds > existingSeconds) candidate else existing
    }
    val existingMeta = sessionMetaScore(existing)
    val candidateMeta = sessionMetaScore(candidate)
    return if (candidateMeta > existingMeta) candidate else existing
}

private fun sessionMetaScore(session: SessionDto): Int {
    var score = 0
    if (session.comment.isNotBlank()) {
        score += 1
    }
    if (!session.bitrixRecordId.isNullOrBlank()) {
        score += 2
    }
    return score
}

private fun sessionDurationSeconds(session: SessionDto): Long {
    val start = parseInstant(session.startedAt) ?: return 0L
    val end = session.endedAt?.let(::parseInstant) ?: start
    return (end.epochSecond - start.epochSecond).coerceAtLeast(0)
}

private fun taskRicher(candidate: TaskDto, current: TaskDto): Boolean {
    if (candidate.sessions.size != current.sessions.size) {
        return candidate.sessions.size > current.sessions.size
    }
    val candidateSeconds = sessionTotalSeconds(candidate)
    val currentSeconds = sessionTotalSeconds(current)
    if (candidateSeconds != currentSeconds) {
        return candidateSeconds > currentSeconds
    }
    return candidate.createdAt >= current.createdAt
}

private fun sessionTotalSeconds(task: TaskDto): Long {
    return task.sessions.sumOf { session -> sessionDurationSeconds(session) }
}
