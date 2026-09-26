package com.timerapp.linkb24.data

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class FocusTimerTest {
    private val now = Instant.parse("2026-09-26T10:00:00Z")
    private fun task(id: String) = TaskDto(id = id, day = "2026-09-26", title = id)

    @Test fun startingFocusPausesOtherTaskAndKeepsOneActiveSession() {
        val other = task("other").copy(status = TaskStatus.RUNNING,
            sessions = listOf(SessionDto("old", now.minusSeconds(60).toString())))
        val data = startFocusTimer(AppDataDto(tasks = listOf(other, task("target"))), "target", 25, now)
        assertEquals(now.toString(), data.tasks[0].sessions.single().endedAt)
        assertEquals(TaskStatus.RUNNING, data.tasks[1].status)
        assertEquals(now.plusSeconds(1500).toString(), data.ui.focusTimer.endsAt)
        assertEquals("other", data.ui.focusTimer.pausedTaskId)
    }

    @Test fun runningTargetSessionIsNotDuplicated() {
        val task = task("target").copy(status = TaskStatus.RUNNING,
            sessions = listOf(SessionDto("existing", now.minusSeconds(30).toString(), comment = "keep")))
        val focused = startFocusTimer(AppDataDto(tasks = listOf(task)), task.id, 1, now)
        assertEquals(task.sessions, focused.tasks.single().sessions)
    }

    @Test fun lateRestoreClosesAtDeadlineAndDoesNotResumeOtherTask() {
        val focused = startFocusTimer(AppDataDto(tasks = listOf(task("target"))), "target", 25, now)
        val restored = reconcileFocusTimer(focused, now.plusSeconds(7200))
        assertEquals(now.plusSeconds(1500).toString(), restored.tasks.single().sessions.single().endedAt)
        assertEquals(TaskStatus.PAUSED, restored.tasks.single().status)
        assertNull(restored.ui.focusTimer.endsAt)
        assertEquals(restored, reconcileFocusTimer(restored, now.plusSeconds(7300)))
    }

    @Test fun earlyStopUsesActualTime() {
        val focused = startFocusTimer(AppDataDto(tasks = listOf(task("target"))), "target", 25, now)
        val stopped = stopFocusTimer(focused, now.plusSeconds(40))
        assertEquals(now.plusSeconds(40).toString(), stopped.tasks.single().sessions.single().endedAt)
        assertEquals(25, stopped.ui.focusTimer.selectedMinutes)
    }

    @Test fun stoppingOrDeletingTargetCancelsFocus() {
        val focused = startFocusTimer(AppDataDto(tasks = listOf(task("target"))), "target", 25, now)
        assertNull(reconcileFocusTimer(focused.copy(tasks = emptyList()), now).ui.focusTimer.endsAt)
        val paused = focused.tasks.single().copy(status = TaskStatus.PAUSED,
            sessions = focused.tasks.single().sessions.map { it.copy(endedAt = now.plusSeconds(1).toString()) })
        assertNull(reconcileFocusTimer(focused.copy(tasks = listOf(paused)), now.plusSeconds(2)).ui.focusTimer.endsAt)
    }

    @Test fun serializationRestoresUnexpiredTimer() {
        val focused = startFocusTimer(AppDataDto(tasks = listOf(task("target"))), "target", 25, now)
        val restored = AppJson.decodeFromString(AppDataDto.serializer(), AppJson.encodeToString(AppDataDto.serializer(), focused))
        assertEquals(focused, reconcileFocusTimer(restored, now.plusSeconds(20)))
    }

    @Test(expected = IllegalArgumentException::class) fun rejectsSecondFocus() {
        val focused = startFocusTimer(AppDataDto(tasks = listOf(task("target"))), "target", 25, now)
        startFocusTimer(focused, "target", 10, now.plusSeconds(1))
    }

    @Test(expected = IllegalArgumentException::class) fun rejectsInvalidMinutes() {
        startFocusTimer(AppDataDto(tasks = listOf(task("target"))), "target", 0, now)
    }
}
