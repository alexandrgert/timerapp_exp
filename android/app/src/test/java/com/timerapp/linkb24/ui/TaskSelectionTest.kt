package com.timerapp.linkb24.ui

import com.timerapp.linkb24.data.TaskDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskSelectionTest {
    @Test
    fun enter_selection_selects_first_task() {
        val selected = enterSelection("task-1")

        assertEquals(setOf("task-1"), selected)
        assertTrue(selected.isNotEmpty())
    }

    @Test
    fun toggle_selection_clears_last_checked_task() {
        val selected = toggleSelection(setOf("task-1"), "task-1")

        assertTrue(selected.isEmpty())
    }

    @Test
    fun next_selection_after_mutation_clears_only_submitted_ids() {
        val selected = nextSelectionAfterMutation(
            selectedTaskIds = setOf("task-1", "task-2", "task-3"),
            tasks = listOf(task("task-1"), task("task-2"), task("task-3")),
            clearSelectionIds = setOf("task-1", "task-2"),
        )

        assertEquals(setOf("task-3"), selected)
    }

    @Test
    fun next_selection_after_mutation_prunes_removed_tasks() {
        val selected = nextSelectionAfterMutation(
            selectedTaskIds = linkedSetOf("task-1", "task-2"),
            tasks = listOf(task("task-2")),
        )

        assertEquals(linkedSetOf("task-2"), selected)
    }

    private fun task(id: String): TaskDto {
        return TaskDto(
            id = id,
            day = "2026-07-30",
            title = id,
        )
    }
}
