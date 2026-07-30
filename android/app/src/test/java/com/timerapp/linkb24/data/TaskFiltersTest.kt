package com.timerapp.linkb24.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskFiltersTest {
    @Test
    fun today_filter_uses_planned_days() {
        val data = AppDataDto(
            tasks = listOf(
                task("a", plannedDays = listOf("2026-06-28")),
                task("b", plannedDays = listOf("2026-06-27")),
            ),
        )

        val filtered = filterTasks(data, TaskViewFilter.TODAY, today = "2026-06-28")

        assertEquals(listOf("a"), filtered.map { it.id })
    }

    @Test
    fun in_progress_excludes_completed() {
        val data = AppDataDto(
            tasks = listOf(
                task("open"),
                task("done", status = TaskStatus.COMPLETED),
            ),
        )

        val filtered = filterTasks(data, TaskViewFilter.IN_PROGRESS)

        assertEquals(listOf("open"), filtered.map { it.id })
    }

    @Test
    fun all_includes_completed_at_bottom() {
        val data = AppDataDto(
            tasks = listOf(
                task("done", status = TaskStatus.COMPLETED, createdAt = "2026-06-28T12:00:00+03:00"),
                task("open", createdAt = "2026-06-28T11:00:00+03:00"),
            ),
        )

        val filtered = filterTasks(data, TaskViewFilter.ALL)

        assertEquals(listOf("open", "done"), filtered.map { it.id })
    }

    @Test
    fun active_task_moves_to_top() {
        val running = task(
            id = "running",
            status = TaskStatus.RUNNING,
            createdAt = "2026-06-28T09:00:00+03:00",
            sessions = listOf(
                SessionDto(id = "s1", startedAt = "2026-06-28T10:00:00+03:00"),
            ),
        )
        val data = AppDataDto(
            tasks = listOf(
                task("newer", createdAt = "2026-06-28T11:00:00+03:00"),
                running,
            ),
        )

        val filtered = filterTasks(data, TaskViewFilter.IN_PROGRESS)

        assertEquals("running", filtered.first().id)
    }

    @Test
    fun today_hides_carried_plan_without_priority() {
        val data = AppDataDto(
            tasks = listOf(
                task(
                    "old",
                    day = "2026-06-27",
                    plannedDays = listOf("2026-06-28"),
                ),
                task(
                    "prio",
                    day = "2026-06-27",
                    plannedDays = listOf("2026-06-28"),
                    dailyPriorities = mapOf("2026-06-28" to 2),
                ),
            ),
        )

        val filtered = filterTasks(data, TaskViewFilter.TODAY, today = "2026-06-28")

        assertEquals(listOf("prio"), filtered.map { it.id })
    }

    @Test
    fun needs_priority_before_start_for_resume_and_open_tasks() {
        val openTask = task("open")
        val completedTask = task("done", status = TaskStatus.COMPLETED)
        val prioritizedTask = task(
            "prio",
            dailyPriorities = mapOf("2026-06-28" to 2),
        )
        val runningTask = task(
            "running",
            status = TaskStatus.RUNNING,
            sessions = listOf(SessionDto(id = "s1", startedAt = "2026-06-28T10:00:00+03:00")),
        )

        assertTrue(needsPriorityBeforeStart(openTask, "2026-06-28"))
        assertTrue(needsPriorityBeforeStart(completedTask, "2026-06-28"))
        assertTrue(!needsPriorityBeforeStart(prioritizedTask, "2026-06-28"))
        assertTrue(!needsPriorityBeforeStart(runningTask, "2026-06-28"))
    }

    private fun task(
        id: String,
        status: TaskStatus = TaskStatus.OPEN,
        createdAt: String = "2026-06-28T10:00:00+03:00",
        day: String = "2026-06-28",
        plannedDays: List<String> = listOf("2026-06-28"),
        sessions: List<SessionDto> = emptyList(),
        dailyPriorities: Map<String, Int> = emptyMap(),
    ): TaskDto {
        return TaskDto(
            id = id,
            day = day,
            title = id,
            status = status,
            createdAt = createdAt,
            plannedDays = plannedDays,
            sessions = sessions,
            dailyPriorities = dailyPriorities,
        )
    }
}
