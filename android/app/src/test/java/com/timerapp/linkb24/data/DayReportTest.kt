package com.timerapp.linkb24.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DayReportTest {
    @Test
    fun short_report_includes_result_and_skips_description() {
        val data = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "t1",
                    day = "2026-07-10",
                    title = "Task A",
                    description = "Long description",
                    result = "Готово",
                    sessions = listOf(
                        SessionDto(
                            id = "s1",
                            startedAt = "2026-07-10T10:00:00+03:00",
                            endedAt = "2026-07-10T12:15:00+03:00",
                        ),
                    ),
                ),
            ),
        )
        val report = buildDayReportMarkdown(data, "2026-07-10", extended = false)
        assertTrue(report.contains("Task A"))
        assertTrue(report.contains("**Результат:** Готово"))
        assertFalse(report.contains("### Описание"))
        assertFalse(report.contains("Сессии за день"))
    }

    @Test
    fun extended_report_includes_sessions() {
        val data = AppDataDto(
            tasks = listOf(
                TaskDto(
                    id = "t1",
                    day = "2026-07-10",
                    title = "Task A",
                    description = "Details",
                    result = "Done",
                    sessions = listOf(
                        SessionDto(
                            id = "s1",
                            startedAt = "2026-07-10T10:00:00+03:00",
                            endedAt = "2026-07-10T11:00:00+03:00",
                            comment = "Note",
                            bitrixRecordId = "7",
                        ),
                    ),
                ),
            ),
        )
        val report = buildDayReportMarkdown(data, "2026-07-10", extended = true)
        assertTrue(report.contains("### Описание"))
        assertTrue(report.contains("Details"))
        assertTrue(report.contains("Сессии за день"))
        assertTrue(report.contains("Note"))
        assertTrue(report.contains("7"))
    }

    @Test
    fun empty_day_message() {
        val report = buildDayReportMarkdown(AppDataDto(), "2026-07-10")
        assertTrue(report.contains("время не учтено"))
    }

    @Test
    fun invalid_date_does_not_throw() {
        val report = buildDayReportMarkdown(AppDataDto(), "2026-07-")
        assertTrue(report.contains("ГГГГ-ММ-ДД"))
    }
}
