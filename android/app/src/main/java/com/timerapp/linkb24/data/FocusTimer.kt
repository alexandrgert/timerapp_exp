package com.timerapp.linkb24.data

import java.time.Instant
import java.util.UUID

/** Same JSON fields as desktop; Android focuses the chosen task rather than creating a synthetic task. */
fun startFocusTimer(data: AppDataDto, taskId: String, minutes: Int, now: Instant = Instant.now()): AppDataDto {
    require(data.tasks.sumOf { t -> t.sessions.count { it.endedAt == null } } <= 1) { "Сначала разрешите одновременные таймеры." }
    require(minutes in 1..180) { "Укажите от 1 до 180 минут." }
    val ready = reconcileFocusTimer(data, now)
    require(ready.ui.focusTimer.endsAt == null) { "Сначала остановите текущую концентрацию." }
    val target = ready.tasks.firstOrNull { it.id == taskId }
        ?: throw IllegalArgumentException("Задача не найдена.")
    require(target.status != TaskStatus.COMPLETED) { "Сначала возобновите завершённую задачу." }
    val previous = ready.tasks.firstOrNull { it.id != taskId && isActive(it) }?.id
    val tasks = ready.tasks.map { task ->
        if (task.id == taskId) {
            val sessions = if (task.sessions.any { it.endedAt == null }) task.sessions else
                task.sessions + SessionDto(UUID.randomUUID().toString(), now.toString())
            task.copy(status = TaskStatus.RUNNING, sessions = sessions)
        } else pauseFocusTask(task, now)
    }
    return ready.copy(tasks = tasks, ui = ready.ui.copy(focusTimer = FocusTimerDto(
        selectedMinutes = minutes, durationMinutes = minutes,
        endsAt = now.plusSeconds(minutes * 60L).toString(), sessionTaskId = taskId,
        pausedTaskId = previous,
    )))
}

fun stopFocusTimer(data: AppDataDto, now: Instant = Instant.now()): AppDataDto {
    val focus = data.ui.focusTimer
    val deadline = focus.endsAt?.let(::parseInstant)
    val end = if (deadline != null && deadline.isBefore(now)) deadline else now
    return data.copy(
        tasks = data.tasks.map { if (it.id == focus.sessionTaskId) pauseFocusTask(it, end) else it },
        ui = data.ui.copy(focusTimer = FocusTimerDto(selectedMinutes = focus.selectedMinutes.coerceIn(1, 180))),
    )
}

/** Reconcile before persistence and after reload; background delays never add time past ends_at. */
fun reconcileFocusTimer(data: AppDataDto, now: Instant = Instant.now()): AppDataDto {
    val focus = data.ui.focusTimer
    if (focus.endsAt == null || data.syncConflicts.isNotEmpty() || data.tasks.sumOf { t -> t.sessions.count { it.endedAt == null } } > 1) return data
    val end = parseInstant(focus.endsAt)
    val task = data.tasks.firstOrNull { it.id == focus.sessionTaskId }
    if (end == null || task == null || task.status != TaskStatus.RUNNING || task.sessions.none { it.endedAt == null }) {
        return data.copy(ui = data.ui.copy(focusTimer = FocusTimerDto(
            selectedMinutes = focus.selectedMinutes.coerceIn(1, 180),
        )))
    }
    return if (!now.isBefore(end)) stopFocusTimer(data, end) else data
}

private fun pauseFocusTask(task: TaskDto, end: Instant): TaskDto {
    if (!isActive(task)) return task
    return task.copy(
        status = if (task.status == TaskStatus.COMPLETED) task.status else TaskStatus.PAUSED,
        sessions = task.sessions.map { session ->
            if (session.endedAt != null) session else {
                // An externally edited future start must not produce negative elapsed time.
                val start = parseInstant(session.startedAt)
                session.copy(endedAt = (if (start != null && start.isAfter(end)) start else end).toString())
            }
        },
    )
}
