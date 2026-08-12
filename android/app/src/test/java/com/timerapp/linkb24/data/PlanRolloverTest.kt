package com.timerapp.linkb24.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlanRolloverTest {
    @Test
    fun ensurePlanRollover_copies_priority_when_keepPriority() {
        val today = "2026-08-12"
        val yesterday = "2026-08-11"
        val data = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "t1",
                    day = yesterday,
                    title = "Keep",
                    plannedDays = listOf(yesterday),
                    dailyPriorities = mapOf(yesterday to 2),
                    keepPriority = true,
                    createdAt = "${yesterday}T10:00:00+03:00",
                ),
            ),
            ui = UiSettingsDto(planRolloverDay = yesterday),
        )

        val result = ensurePlanRollover(data, today)

        assertTrue(result.changed)
        val task = result.data.tasks.single()
        assertTrue(today in task.plannedDays)
        assertEquals(2, task.dailyPriorities[today])
        assertEquals(today, result.data.ui.planRolloverDay)
    }

    @Test
    fun ensurePlanRollover_without_keep_leaves_today_without_priority() {
        val today = "2026-08-12"
        val yesterday = "2026-08-11"
        val data = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "t1",
                    day = yesterday,
                    title = "No keep",
                    plannedDays = listOf(yesterday),
                    dailyPriorities = mapOf(yesterday to 1),
                    keepPriority = false,
                    createdAt = "${yesterday}T10:00:00+03:00",
                ),
            ),
            ui = UiSettingsDto(planRolloverDay = yesterday),
        )

        val result = ensurePlanRollover(data, today)
        val task = result.data.tasks.single()
        assertTrue(today in task.plannedDays)
        assertFalse(today in task.dailyPriorities)
    }

    @Test
    fun ensurePlanRollover_runs_once_per_day() {
        val today = "2026-08-12"
        val data = AppDataDto(ui = UiSettingsDto(planRolloverDay = today))
        val result = ensurePlanRollover(data, today)
        assertFalse(result.changed)
    }
}
