package com.timerapp.linkb24.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.io.path.createTempDirectory

class TaskRepositoryTest {
    private fun tempDir(): File = createTempDirectory("taskrepo-test-").toFile()

    @Test
    fun load_returns_empty_when_files_missing() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))

        val loaded = repository.load()

        assertTrue(loaded.tasks.isEmpty())
    }

    @Test
    fun save_is_atomic_and_creates_backup() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val data = repository.createTask("First", AppDataDto())

        repository.save(data)
        val updated = repository.createTask("Second", data)
        repository.save(updated)

        assertTrue(File(dir, "data.json").isFile)
        assertTrue(File(dir, "data.json.bak").isFile)
        assertEquals(2, repository.load().tasks.size)
    }

    @Test
    fun load_recovers_from_backup_when_main_file_corrupt() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val first = repository.createTask("Backup task", AppDataDto())
        repository.save(first)
        repository.save(first)
        File(dir, "data.json").writeText("{ broken")

        val loaded = repository.load()

        assertEquals("Backup task", loaded.tasks.single().title)
    }

    @Test
    fun load_accepts_null_focus_timer_duration() {
        val dir = tempDir()
        val file = File(dir, "data.json")
        file.writeText(
            """
            {
              "tasks": [],
              "ui": {
                "schema_version": 2,
                "focus_timer": {
                  "selected_minutes": 25,
                  "duration_minutes": null,
                  "ends_at": null
                }
              }
            }
            """.trimIndent(),
        )
        val repository = TaskRepository(file)

        val loaded = repository.load()

        assertNull(loaded.ui.focusTimer.durationMinutes)
    }

    @Test
    fun parseInstant_returns_null_for_invalid_value() {
        assertNull(parseInstant(""))
        assertNull(parseInstant("not-a-date"))
    }

    @Test
    fun startTask_does_not_duplicate_open_session() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val created = repository.createTask("Timer", AppDataDto())
        val running = repository.toggleTimer(created.tasks.single().id, created)
        val resumed = repository.toggleTimer(running.tasks.single().id, running)

        assertEquals(1, resumed.tasks.single().sessions.size)
    }

    @Test
    fun parseInstant_parses_offset_datetime() {
        val instant = parseInstant("2026-06-15T10:00:00+03:00")
        assertNotNull(instant)
    }

    @Test
    fun resumeCompletedTask_reopens_and_starts_timer() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val created = repository.createTask("Done", AppDataDto())
        val completed = repository.completeTask(created.tasks.single().id, created, result = "Готово")
        val task = completed.tasks.single()

        assertEquals(TaskStatus.COMPLETED, task.status)
        assertEquals("Готово", task.result)
        assertNotNull(task.completedAt)

        val resumed = repository.resumeCompletedTask(task.id, completed, comment = "Доработка")
        val reopened = resumed.tasks.single()

        assertEquals(TaskStatus.RUNNING, reopened.status)
        assertNull(reopened.completedAt)
        assertEquals(1, reopened.sessions.size)
        assertNull(reopened.sessions.single().endedAt)
        assertEquals("Доработка", reopened.sessions.single().comment)
    }

    @Test
    fun completeTask_requires_non_blank_result() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val created = repository.createTask("Need result", AppDataDto())
        try {
            repository.completeTask(created.tasks.single().id, created, result = "  ")
            throw AssertionError("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
            // expected
        }
    }

    @Test
    fun updateTask_rejects_empty_result_for_completed() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val created = repository.createTask("Done", AppDataDto())
        val completed = repository.completeTask(created.tasks.single().id, created, result = "Ok")
        try {
            repository.updateTask(completed.tasks.single().id, completed, result = "  ")
            throw AssertionError("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
            // expected
        }
    }

    @Test
    fun addClosedSession_appends_hour_interval() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val created = repository.createTask("Hist", AppDataDto())
        val taskId = created.tasks.single().id
        val updated = repository.addClosedSession(
            taskId,
            created,
            startedAt = "2026-08-12T15:30:00+03:00",
            endedAt = "2026-08-12T16:30:00+03:00",
        )
        val session = updated.tasks.single().sessions.single()
        assertEquals("2026-08-12T15:30:00+03:00", session.startedAt)
        assertEquals("2026-08-12T16:30:00+03:00", session.endedAt)
        assertEquals("", session.comment)
    }
}
