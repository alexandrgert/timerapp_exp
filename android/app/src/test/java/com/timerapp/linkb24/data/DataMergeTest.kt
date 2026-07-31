package com.timerapp.linkb24.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import com.timerapp.linkb24.webdav.contentHash
import com.timerapp.linkb24.webdav.metaRemotePath
import com.timerapp.linkb24.webdav.newMeta

class DataMergeTest {
    @Test
    fun mergeAppData_keeps_richer_task_by_sessions() {
        val local = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "t1",
                    day = "2026-06-17",
                    title = "Local",
                    createdAt = "2026-06-17T10:00:00+03:00",
                    sessions = listOf(
                        SessionDto("s1", "2026-06-17T10:00:00+03:00", "2026-06-17T10:05:00+03:00"),
                    ),
                ),
            ),
        )
        val remote = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "t1",
                    day = "2026-06-17",
                    title = "Remote",
                    createdAt = "2026-06-17T09:00:00+03:00",
                    sessions = listOf(
                        SessionDto("s1", "2026-06-17T10:00:00+03:00", "2026-06-17T10:05:00+03:00"),
                        SessionDto("s2", "2026-06-17T11:00:00+03:00", "2026-06-17T11:10:00+03:00"),
                    ),
                ),
            ),
        )

        val merged = mergeAppData(listOf(local, remote))

        assertEquals(1, merged.tasks.size)
        assertEquals("Remote", merged.tasks.single().title)
        assertEquals(2, merged.tasks.single().sessions.size)
    }

    @Test
    fun normalizeRunningTasks_keeps_latest_running_only() {
        val data = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "old",
                    day = "2026-06-17",
                    title = "Old",
                    status = TaskStatus.RUNNING,
                    createdAt = "2026-06-17T09:00:00+03:00",
                    sessions = listOf(SessionDto("s1", "2026-06-17T09:00:00+03:00")),
                ),
                TaskDto(
                    id = "new",
                    day = "2026-06-17",
                    title = "New",
                    status = TaskStatus.RUNNING,
                    createdAt = "2026-06-17T10:00:00+03:00",
                    sessions = listOf(SessionDto("s2", "2026-06-17T10:00:00+03:00")),
                ),
            ),
        )

        val normalized = normalizeRunningTasks(data)
        val old = normalized.tasks.first { it.id == "old" }
        val newTask = normalized.tasks.first { it.id == "new" }

        assertEquals(TaskStatus.PAUSED, old.status)
        assertEquals(TaskStatus.RUNNING, newTask.status)
        assertFalse(old.sessions.single().endedAt.isNullOrBlank())
    }

    @Test
    fun mergeTaskPair_unions_sessions_from_empty_local_copy() {
        val local = TaskDto(
            id = "t1",
            day = "2026-06-28",
            title = "test webdav1",
            createdAt = "2026-06-28T21:00:00+03:00",
            plannedDays = listOf("2026-06-28"),
        )
        val remote = TaskDto(
            id = "t1",
            day = "2026-06-28",
            title = "test webdav1",
            createdAt = "2026-06-28T20:00:00+03:00",
            plannedDays = listOf("2026-06-28"),
            sessions = listOf(
                SessionDto(
                    id = "s1",
                    startedAt = "2026-06-28T20:31:00+03:00",
                    endedAt = "2026-06-28T20:31:04+03:00",
                ),
            ),
        )

        val merged = mergeTaskPair(local, remote)

        assertEquals(1, merged.sessions.size)
        assertEquals(4L, taskDurationSeconds(merged))
    }

    @Test
    fun mergeTaskPair_keepsCompletedWhenOtherCopyIsRicher() {
        val local = TaskDto(
            id = "t1",
            day = "2026-06-15",
            title = "Local",
            status = TaskStatus.COMPLETED,
            completedAt = "2026-06-15T12:00:00+03:00",
            createdAt = "2026-06-15T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-06-15T10:00:00+03:00", "2026-06-15T11:00:00+03:00"),
                SessionDto("s2", "2026-06-15T11:30:00+03:00", "2026-06-15T12:00:00+03:00"),
            ),
        )
        val remote = TaskDto(
            id = "t1",
            day = "2026-06-15",
            title = "Remote",
            createdAt = "2026-06-15T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-06-15T10:00:00+03:00", "2026-06-15T10:30:00+03:00"),
            ),
        )

        val merged = mergeTaskPair(local, remote)

        assertEquals(TaskStatus.COMPLETED, merged.status)
        assertEquals("2026-06-15T12:00:00+03:00", merged.completedAt)
        assertEquals(2, merged.sessions.size)
    }

    @Test
    fun mergeTaskPair_runningSessionOverridesCompleted() {
        val local = TaskDto(
            id = "t1",
            day = "2026-06-15",
            title = "Local",
            status = TaskStatus.COMPLETED,
            completedAt = "2026-06-15T12:00:00+03:00",
            createdAt = "2026-06-15T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-06-15T10:00:00+03:00", "2026-06-15T11:00:00+03:00"),
            ),
        )
        val remote = TaskDto(
            id = "t1",
            day = "2026-06-15",
            title = "Remote",
            status = TaskStatus.RUNNING,
            createdAt = "2026-06-15T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s2", "2026-06-15T13:00:00+03:00", null),
            ),
        )

        val merged = mergeTaskPair(local, remote)

        assertEquals(TaskStatus.RUNNING, merged.status)
        assertEquals(null, merged.completedAt)
    }

    @Test
    fun mergeTaskPair_pausedWhenSessionsEndedAndNotCompleted() {
        val local = TaskDto(
            id = "t1",
            day = "2026-06-15",
            title = "Local",
            createdAt = "2026-06-15T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-06-15T10:00:00+03:00", "2026-06-15T11:00:00+03:00"),
            ),
        )
        val remote = TaskDto(
            id = "t1",
            day = "2026-06-15",
            title = "Remote",
            createdAt = "2026-06-15T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s2", "2026-06-15T12:00:00+03:00", "2026-06-15T12:30:00+03:00"),
            ),
        )

        val merged = mergeTaskPair(local, remote)

        assertEquals(TaskStatus.PAUSED, merged.status)
        assertEquals(null, merged.completedAt)
        assertEquals(2, merged.sessions.size)
    }

    @Test
    fun normalizeRunningTasks_prefersInstantOverStringCompare() {
        val data = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "offset_early",
                    day = "2026-06-15",
                    title = "Offset",
                    status = TaskStatus.RUNNING,
                    createdAt = "2026-06-15T08:00:00+03:00",
                    sessions = listOf(SessionDto("s1", "2026-06-15T08:00:00+03:00")),
                ),
                TaskDto(
                    id = "naive_later",
                    day = "2026-06-15",
                    title = "Naive",
                    status = TaskStatus.RUNNING,
                    createdAt = "2026-06-15T10:00:00",
                    sessions = listOf(SessionDto("s2", "2026-06-15T10:00:00")),
                ),
            ),
        )

        val normalized = normalizeRunningTasks(data)
        val winner = normalized.tasks.first { it.status == TaskStatus.RUNNING }
        val paused = normalized.tasks.first { it.id == "offset_early" }

        assertEquals("naive_later", winner.id)
        assertEquals(TaskStatus.PAUSED, paused.status)
    }

    @Test
    fun roundTrip_preserves_desktop_fields() {
        val original = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "t1",
                    day = "2026-07-10",
                    title = "Desktop task",
                    description = "Desc",
                    result = "Done",
                    dailyPriorities = mapOf("2026-07-10" to 2),
                    createdAt = "2026-07-10T10:00:00+03:00",
                    sessions = listOf(
                        SessionDto(
                            id = "s1",
                            startedAt = "2026-07-10T10:00:00+03:00",
                            endedAt = "2026-07-10T11:00:00+03:00",
                            comment = "Note",
                            bitrixRecordId = "99",
                        ),
                    ),
                ),
            ),
            ui = UiSettingsDto(priorityFilter = listOf(1, 2)),
        )
        val encoded = AppJson.encodeToString(AppDataDto.serializer(), original)
        val restored = AppJson.decodeFromString(AppDataDto.serializer(), encoded)
        assertEquals("Done", restored.tasks.single().result)
        assertEquals(2, restored.tasks.single().dailyPriorities["2026-07-10"])
        assertEquals("Note", restored.tasks.single().sessions.single().comment)
        assertEquals("99", restored.tasks.single().sessions.single().bitrixRecordId)
        assertEquals(listOf(1, 2), restored.ui.priorityFilter)
    }

    @Test
    fun mergeTaskPair_keeps_result_and_priorities() {
        val local = TaskDto(
            id = "t1",
            day = "2026-07-10",
            title = "Local",
            result = "From local",
            dailyPriorities = mapOf("2026-07-10" to 3),
            createdAt = "2026-07-10T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-07-10T10:00:00+03:00", "2026-07-10T10:30:00+03:00"),
            ),
        )
        val remote = TaskDto(
            id = "t1",
            day = "2026-07-10",
            title = "Remote",
            result = "",
            dailyPriorities = mapOf("2026-07-10" to 1),
            createdAt = "2026-07-10T09:00:00+03:00",
            sessions = listOf(
                SessionDto(
                    "s1",
                    "2026-07-10T10:00:00+03:00",
                    "2026-07-10T10:30:00+03:00",
                    comment = "Resume reason",
                    bitrixRecordId = "42",
                ),
            ),
        )

        val merged = mergeTaskPair(local, remote)
        assertEquals("From local", merged.result)
        assertEquals(1, merged.dailyPriorities["2026-07-10"])
        assertEquals("Resume reason", merged.sessions.single().comment)
        assertEquals("42", merged.sessions.single().bitrixRecordId)
    }

    @Test
    fun pickRicherSession_equalMetaPrefersCandidate() {
        val left = TaskDto(
            id = "t1",
            day = "2026-07-30",
            title = "T",
            createdAt = "2026-07-30T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-07-30T10:00:00+03:00", "2026-07-30T11:00:00+03:00", comment = "a"),
            ),
        )
        val right = TaskDto(
            id = "t1",
            day = "2026-07-30",
            title = "T",
            createdAt = "2026-07-30T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-07-30T10:00:00+03:00", "2026-07-30T11:00:00+03:00", comment = "b"),
            ),
        )
        assertEquals("b", mergeTaskPair(left, right).sessions.single().comment)
    }

    @Test
    fun pickRicherSession_keepsBitrixWhenCandidateBlank() {
        val withBitrix = TaskDto(
            id = "t1",
            day = "2026-07-30",
            title = "T",
            createdAt = "2026-07-30T10:00:00+03:00",
            sessions = listOf(
                SessionDto(
                    "s1",
                    "2026-07-30T10:00:00+03:00",
                    "2026-07-30T10:30:00+03:00",
                    bitrixRecordId = "42",
                ),
            ),
        )
        val withoutBitrix = TaskDto(
            id = "t1",
            day = "2026-07-30",
            title = "T",
            createdAt = "2026-07-30T10:00:00+03:00",
            sessions = listOf(
                SessionDto("s1", "2026-07-30T10:00:00+03:00", "2026-07-30T10:30:00+03:00"),
            ),
        )
        assertEquals("42", mergeTaskPair(withBitrix, withoutBitrix).sessions.single().bitrixRecordId)
        assertEquals("42", mergeTaskPair(withoutBitrix, withBitrix).sessions.single().bitrixRecordId)
    }

    @Test
    fun goldenFixture_bitrixVsPlain() {
        assertGoldenSession("merge_lockstep/case_bitrix_vs_plain")
    }

    @Test
    fun goldenFixture_commentTie() {
        assertGoldenSession("merge_lockstep/case_comment_tie")
    }

    @Test
    fun goldenFixture_unionTwoIds() {
        val left = loadTaskFixture("merge_lockstep/case_union_two_ids/left.json")
        val right = loadTaskFixture("merge_lockstep/case_union_two_ids/right.json")
        val expected = loadTaskFixture("merge_lockstep/case_union_two_ids/expected_task.json")
        val merged = mergeTaskPair(left, right)
        assertEquals(expected.sessions.map { it.id }, merged.sessions.map { it.id })
        assertEquals(
            expected.sessions.map { it.startedAt to it.endedAt },
            merged.sessions.map { it.startedAt to it.endedAt },
        )
    }

    private fun assertGoldenSession(caseDir: String) {
        val left = loadTaskFixture("$caseDir/left.json")
        val right = loadTaskFixture("$caseDir/right.json")
        val expected = loadSessionFixture("$caseDir/expected_session.json")
        val got = mergeTaskPair(left, right).sessions.single()
        assertEquals(expected.id, got.id)
        assertEquals(expected.startedAt, got.startedAt)
        assertEquals(expected.endedAt, got.endedAt)
        assertEquals(expected.comment, got.comment)
        assertEquals(expected.bitrixRecordId, got.bitrixRecordId)
    }

    private fun loadTaskFixture(path: String): TaskDto {
        val stream = requireNotNull(javaClass.classLoader).getResourceAsStream(path)
            ?: error("Missing fixture: $path")
        val text = stream.bufferedReader().use { it.readText() }
        return AppJson.decodeFromString(TaskDto.serializer(), text)
    }

    private fun loadSessionFixture(path: String): SessionDto {
        val stream = requireNotNull(javaClass.classLoader).getResourceAsStream(path)
            ?: error("Missing fixture: $path")
        val text = stream.bufferedReader().use { it.readText() }
        return AppJson.decodeFromString(SessionDto.serializer(), text)
    }
}

class WebDavMetaTest {
    @Test
    fun contentHash_is_stable() {
        val payload = """{"tasks":[]}""".encodeToByteArray()
        assertEquals(contentHash(payload), contentHash(payload))
    }

    @Test
    fun metaRemotePath_replaces_json_suffix() {
        assertEquals(
            "tasktimer/data.sync-meta.json",
            metaRemotePath("tasktimer/data.json"),
        )
    }

    @Test
    fun newMeta_contains_device_id() {
        val payload = "{}".encodeToByteArray()
        val meta = newMeta(payload, "device123")
        assertEquals("device123", meta.deviceId)
        assertEquals(contentHash(payload), meta.contentHash)
    }
}
