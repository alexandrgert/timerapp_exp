package com.timerapp.linkb24.data

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

enum class TaskViewFilter {
    TODAY,
    IN_PROGRESS,
    ALL,
}

fun todayIsoDate(): String {
    return LocalDate.now(ZoneId.systemDefault()).format(DateTimeFormatter.ISO_LOCAL_DATE)
}

fun sessionLocalDate(startedAt: String): String? {
    val instant = parseInstant(startedAt) ?: return null
    return instant.atZone(ZoneId.systemDefault()).toLocalDate().format(DateTimeFormatter.ISO_LOCAL_DATE)
}

fun todaySeconds(task: TaskDto, dateIso: String, nowMillis: Long = System.currentTimeMillis()): Long {
    val nowInstant = Instant.ofEpochMilli(nowMillis)
    return task.sessions.sumOf { session ->
        if (sessionLocalDate(session.startedAt) != dateIso) {
            return@sumOf 0L
        }
        val start = parseInstant(session.startedAt) ?: return@sumOf 0L
        val end = session.endedAt?.let(::parseInstant) ?: nowInstant
        (end.epochSecond - start.epochSecond).coerceAtLeast(0)
    }
}

fun visibleOnTodayPlan(task: TaskDto, today: String): Boolean {
    if (today !in task.plannedDays) {
        return false
    }
    return showInTodayPlan(task, today)
}

fun showInTodayPlan(task: TaskDto, today: String): Boolean {
    if (task.day == today) {
        return true
    }
    if (task.status == TaskStatus.RUNNING && task.sessions.any { it.endedAt == null }) {
        return true
    }
    return hasExplicitPriority(task, today)
}

fun filterTasksByTitle(tasks: List<TaskDto>, needle: String): List<TaskDto> {
    val query = needle.trim().lowercase()
    if (query.isEmpty()) {
        return tasks
    }
    return tasks.filter { query in it.title.lowercase() }
}

fun filterTasks(
    data: AppDataDto,
    filter: TaskViewFilter,
    today: String = todayIsoDate(),
    priorityLevels: Set<Int> = priorityFilterLevels(data.ui),
): List<TaskDto> {
    val filtered = when (filter) {
        TaskViewFilter.TODAY -> {
            val todayTasks = data.tasks.filter { visibleOnTodayPlan(it, today) }
            val runningIds = data.tasks
                .filter { it.status == TaskStatus.RUNNING }
                .map { it.id }
                .toSet()
            todayTasks.filter { task ->
                task.id in runningIds || taskPriority(task, today) in priorityLevels
            }
        }
        TaskViewFilter.IN_PROGRESS -> data.tasks
            .filter { it.status != TaskStatus.COMPLETED }
            .filter { taskPriority(it, today) in priorityLevels }
        TaskViewFilter.ALL -> data.tasks.filter { taskPriority(it, today) in priorityLevels }
    }
    return sortTasksForView(filtered, data.tasks, today)
}

fun sortTasksForView(
    tasks: List<TaskDto>,
    allTasks: List<TaskDto>,
    today: String = todayIsoDate(),
): List<TaskDto> {
    val activeTask = allTasks.firstOrNull(::isActive)
    return tasks.sortedWith(
        compareBy<TaskDto> { task ->
            when {
                activeTask != null && task.id == activeTask.id -> 0
                task.status == TaskStatus.COMPLETED -> 2
                else -> 1
            }
        }.thenBy { taskPriority(it, today) }
            .thenByDescending { it.createdAt },
    )
}
