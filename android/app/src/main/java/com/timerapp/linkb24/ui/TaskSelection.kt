package com.timerapp.linkb24.ui

import com.timerapp.linkb24.data.TaskDto

fun enterSelection(taskId: String): Set<String> {
    return setOf(taskId)
}

fun toggleSelection(selectedTaskIds: Set<String>, taskId: String): Set<String> {
    return if (taskId in selectedTaskIds) {
        selectedTaskIds - taskId
    } else {
        selectedTaskIds + taskId
    }
}

fun pruneSelection(selectedTaskIds: Set<String>, tasks: List<TaskDto>): Set<String> {
    val existingIds = tasks.mapTo(linkedSetOf()) { it.id }
    return selectedTaskIds.filterTo(linkedSetOf()) { it in existingIds }
}

fun nextSelectionAfterMutation(
    selectedTaskIds: Set<String>,
    tasks: List<TaskDto>,
    clearSelectionIds: Set<String> = emptySet(),
): Set<String> {
    val remaining = if (clearSelectionIds.isEmpty()) {
        selectedTaskIds
    } else {
        selectedTaskIds - clearSelectionIds
    }
    return pruneSelection(remaining, tasks)
}
