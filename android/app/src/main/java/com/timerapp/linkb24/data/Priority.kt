package com.timerapp.linkb24.data

const val DEFAULT_PRIORITY = 4
const val MIN_PRIORITY = 1
const val MAX_PRIORITY = 4
val ALL_PRIORITIES: Set<Int> = setOf(1, 2, 3, 4)

fun normalizePriority(value: Int?): Int {
    if (value == null || value < MIN_PRIORITY || value > MAX_PRIORITY) {
        return DEFAULT_PRIORITY
    }
    return value
}

fun taskPriority(task: TaskDto, dateIso: String): Int {
    return normalizePriority(task.dailyPriorities[dateIso])
}

fun hasExplicitPriority(task: TaskDto, dateIso: String): Boolean {
    return dateIso in task.dailyPriorities
}

fun needsPriorityBeforeStart(task: TaskDto, dateIso: String): Boolean {
    if (task.status == TaskStatus.RUNNING || isActive(task)) {
        return false
    }
    return !hasExplicitPriority(task, dateIso)
}

fun mergeDailyPriorities(
    left: Map<String, Int>,
    right: Map<String, Int>,
): Map<String, Int> {
    val merged = linkedMapOf<String, Int>()
    for (key in left.keys + right.keys) {
        val leftValue = storedPriority(left[key])
        val rightValue = storedPriority(right[key])
        when {
            leftValue != null && rightValue != null -> merged[key] = minOf(leftValue, rightValue)
            leftValue != null -> merged[key] = leftValue
            rightValue != null -> merged[key] = rightValue
        }
    }
    return merged
}

fun priorityFilterLevels(ui: UiSettingsDto): Set<Int> {
    val levels = ui.priorityFilter
        .filter { it in ALL_PRIORITIES }
        .toSet()
    return levels.ifEmpty { ALL_PRIORITIES }
}

fun withPriorityFilter(ui: UiSettingsDto, levels: Set<Int>): UiSettingsDto {
    val normalized = levels.filter { it in ALL_PRIORITIES }.sorted()
    if (normalized.isEmpty()) {
        return ui
    }
    return ui.copy(priorityFilter = normalized)
}

fun withTaskPriority(task: TaskDto, dateIso: String, priority: Int): TaskDto {
    val clamped = normalizePriority(priority)
    val updated = task.dailyPriorities.toMutableMap()
    updated[dateIso] = clamped
    return task.copy(dailyPriorities = updated)
}

fun clearTaskPriority(task: TaskDto, dateIso: String): TaskDto {
    if (dateIso !in task.dailyPriorities) {
        return task
    }
    return task.copy(dailyPriorities = task.dailyPriorities - dateIso)
}

private fun storedPriority(value: Int?): Int? {
    if (value == null || value < MIN_PRIORITY || value > MAX_PRIORITY) {
        return null
    }
    return value
}
