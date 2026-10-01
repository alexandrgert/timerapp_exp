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
        repository.mutate { updated }

        assertTrue(File(dir, "data.json").isFile)
        assertTrue(File(dir, "data.json.bak").isFile)
        assertEquals(2, repository.load().tasks.size)
    }

    @Test
    fun corrupt_file_requires_explicit_restore_and_rotates_actor() {
        val dir = tempDir()
        val repository = TaskRepository(File(dir, "data.json"))
        val first = repository.createTask("Backup task", AppDataDto())
        repository.save(first)
        repository.mutate { first }
        File(dir, "data.json").writeText("{ broken")

        org.junit.Assert.assertThrows(Exception::class.java) { repository.load() }
        val backup = kotlinx.serialization.json.Json.parseToJsonElement(File(dir, "data.json.bak").readText()) as kotlinx.serialization.json.JsonObject
        // A corrupt main file must not silently resurrect older/deleted data.
        assertTrue(File(dir, "data.json").readText().contains("broken"))
        val restored = repository.restoreBackup(backup)
        assertEquals("Backup task", restored.tasks.single().title)
        val current = kotlinx.serialization.json.Json.parseToJsonElement(File(dir, "data.json").readText()) as kotlinx.serialization.json.JsonObject
        org.junit.Assert.assertNotEquals(backup["_sync_actor"], current["_sync_actor"])
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
    @Test
    fun edited_session_preserves_identity_and_transfer_and_can_shorten_time() {
        val repo = TaskRepository(File(tempDir(), "data.json"))
        val session = SessionDto("s", "2026-08-12T23:30:12.123456789+03:00", "2026-08-13T01:30:00+03:00", "b24", "old")
        val data = AppDataDto(tasks = listOf(TaskDto("t", "2026-08-12", "Task", createdAt = "2026-08-12T09:00:00Z", sessions = listOf(session))))
        val updated = repo.updateSession("t", "s", data, session.startedAt, "2026-08-13T00:00:12.123456789+03:00", "")
        assertEquals(session.copy(endedAt = "2026-08-13T00:00:12.123456789+03:00", comment = ""), updated.tasks.single().sessions.single())
        assertEquals(1800L, taskDurationSeconds(updated.tasks.single()))
        repo.mutate { updated }
        assertEquals(updated.tasks.single().sessions, repo.load().tasks.single().sessions)
    }

    @Test fun active_session_can_be_commented_closed_or_deleted() {
        val repo = TaskRepository(File(tempDir(), "data.json"))
        val session = SessionDto("s", "2026-08-12T10:00:12.123456789+03:00")
        val data = AppDataDto(tasks = listOf(TaskDto("t", "2026-08-12", "Task", createdAt = "2026-08-12T09:00:00Z", status = TaskStatus.RUNNING, sessions = listOf(session))))
        val commented = repo.updateSession("t", "s", data, session.startedAt, null, "note")
        assertEquals(TaskStatus.RUNNING, commented.tasks.single().status)
        assertEquals(session.copy(comment = "note"), commented.tasks.single().sessions.single())
        val closed = repo.updateSession("t", "s", commented, session.startedAt, "2026-08-12T11:00:00+03:00", "note")
        assertEquals(TaskStatus.PAUSED, closed.tasks.single().status)
        val deleted = repo.deleteSession("t", "s", data)
        assertEquals(TaskStatus.OPEN, deleted.tasks.single().status)
        assertEquals(0L, taskDurationSeconds(deleted.tasks.single()))
        repo.mutate { deleted }
        assertTrue(repo.load().tasks.single().sessions.isEmpty())
    }

    @Test fun completed_task_stays_completed_after_session_changes() {
        val repo = TaskRepository(File(tempDir(), "data.json"))
        val task = TaskDto("t", "2026-08-12", "Task", createdAt = "2026-08-12T09:00:00Z", status = TaskStatus.COMPLETED, completedAt = "2026-08-12T12:00:00Z", result = "Done")
        val added = repo.addClosedSession("t", AppDataDto(tasks = listOf(task)), "2026-08-11T23:00:00Z", "2026-08-12T01:00:00Z", "new")
        val session = added.tasks.single().sessions.single()
        val edited = repo.updateSession("t", session.id, added, session.startedAt, session.endedAt, "")
        val deleted = repo.deleteSession("t", session.id, edited)
        assertEquals(task, deleted.tasks.single())
        assertEquals(TaskStatus.COMPLETED, edited.tasks.single().status)
    }

    @Test fun session_mutations_reject_missing_records_and_invalid_ranges() {
        val repo = TaskRepository(File(tempDir(), "data.json"))
        val session = SessionDto("s", "2026-08-12T10:00:00Z", "2026-08-12T11:00:00Z")
        val data = AppDataDto(tasks = listOf(TaskDto("t", "2026-08-12", "Task", createdAt = "2026-08-12T09:00:00Z", sessions = listOf(session))))
        fun rejected(action: () -> Any) {
            try { action(); throw AssertionError("Expected validation error") } catch (_: IllegalArgumentException) { }
        }
        rejected { repo.addClosedSession("missing", data, session.startedAt, session.endedAt!!) }
        rejected { repo.updateSession("missing", "s", data, session.startedAt, session.endedAt, "") }
        rejected { repo.updateSession("t", "missing", data, session.startedAt, session.endedAt, "") }
        rejected { repo.deleteSession("missing", "s", data) }
        rejected { repo.deleteSession("t", "missing", data) }
        rejected { repo.deleteTask("missing", data) }
        rejected { repo.updateSession("t", "s", data, session.startedAt, null, "") }
        rejected { repo.updateSession("t", "s", data, session.startedAt, session.startedAt, "") }
        rejected { repo.addClosedSession("t", data, "2026-02-30T10:00:00Z", session.endedAt!!) }
        rejected { repo.addClosedSession("t", data, session.endedAt!!, session.startedAt) }
        assertEquals(session, data.tasks.single().sessions.single())
    }

    @Test fun deleting_closed_session_keeps_other_running_session() {
        val repo = TaskRepository(File(tempDir(), "data.json"))
        val active = SessionDto("active", "2026-08-12T12:00:00Z")
        val old = SessionDto("old", "2026-08-12T10:00:00Z", "2026-08-12T11:00:00Z")
        val data = AppDataDto(tasks = listOf(TaskDto("t", "2026-08-12", "Task", createdAt = "2026-08-12T09:00:00Z", status = TaskStatus.RUNNING, sessions = listOf(old, active))))
        val deleted = repo.deleteSession("t", "old", data).tasks.single()
        assertEquals(TaskStatus.RUNNING, deleted.status)
        assertEquals(listOf(active), deleted.sessions)
        assertTrue(repo.deleteTask("t", data).tasks.isEmpty())
    }
}
