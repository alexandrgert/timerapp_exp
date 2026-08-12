package com.timerapp.linkb24.data

import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val zoneId: ZoneId = ZoneId.systemDefault()

data class PlanRolloverResult(
    val data: AppDataDto,
    val changed: Boolean,
)

/**
 * Carry yesterday's unfinished plan into today (desktop [ensure_plan_rollover] parity).
 * When [TaskDto.keepPriority] is set, copy yesterday's daily priority onto today.
 */
fun ensurePlanRollover(
    data: AppDataDto,
    today: String = todayIsoDate(),
): PlanRolloverResult {
    var current = closeCrossDayActiveTasks(data, today)
    var changed = current != data
    if (current.ui.planRolloverDay == today) {
        return PlanRolloverResult(current, changed)
    }
    val yesterday = LocalDate.parse(today).minusDays(1).format(DateTimeFormatter.ISO_LOCAL_DATE)
    changed = true
    val tasks = current.tasks.map { task ->
        if (task.status == TaskStatus.COMPLETED) {
            return@map task
        }
        if (yesterday in task.plannedDays && today !in task.plannedDays) {
            var updated = task.copy(plannedDays = task.plannedDays + today)
            val yesterdayPriority = task.dailyPriorities[yesterday]
            if (task.keepPriority && yesterdayPriority != null) {
                updated = updated.copy(
                    dailyPriorities = updated.dailyPriorities + (today to yesterdayPriority),
                )
            }
            updated
        } else {
            task
        }
    }
    current = current.copy(
        tasks = tasks,
        ui = current.ui.copy(planRolloverDay = today),
    )
    return PlanRolloverResult(current, changed = true)
}

fun closeCrossDayActiveTasks(data: AppDataDto, today: String): AppDataDto {
    var changed = false
    val tasks = data.tasks.map { task ->
        val active = task.sessions.lastOrNull { it.endedAt == null } ?: return@map task
        val startDate = sessionLocalDate(active.startedAt) ?: return@map task
        if (startDate == today) {
            return@map task
        }
        changed = true
        val endOfStartDay = LocalDate.parse(startDate)
            .atTime(LocalTime.of(23, 59, 59))
            .atZone(zoneId)
            .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val sessions = task.sessions.map { session ->
            if (session.id == active.id) session.copy(endedAt = endOfStartDay) else session
        }
        task.copy(status = TaskStatus.PAUSED, sessions = sessions)
    }
    return if (changed) data.copy(tasks = tasks) else data
}
