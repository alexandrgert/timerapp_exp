package com.timerapp.linkb24.data

import java.time.Instant
import java.time.LocalDate
import java.time.format.DateTimeFormatter

private val dayLabelFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("dd.MM.yyyy")

fun formatHm(totalSeconds: Long): String {
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    return String.format("%02d:%02d", hours, minutes)
}

fun formatDayLabel(dateIso: String): String {
    return LocalDate.parse(dateIso).format(dayLabelFormatter)
}

fun parseIsoDateOrNull(dateIso: String): LocalDate? {
    return runCatching { LocalDate.parse(dateIso.trim()) }.getOrNull()
}

fun buildDayReportMarkdown(
    data: AppDataDto,
    dateIso: String,
    extended: Boolean = false,
    nowMillis: Long = System.currentTimeMillis(),
): String {
    val parsed = parseIsoDateOrNull(dateIso)
        ?: return "Укажите дату в формате ГГГГ-ММ-ДД."
    val normalized = parsed.format(DateTimeFormatter.ISO_LOCAL_DATE)
    val dayLabel = formatDayLabel(normalized)
    val tasks = data.tasks
        .filter { todaySeconds(it, normalized, nowMillis) > 0 }
        .sortedByDescending { todaySeconds(it, normalized, nowMillis) }
    if (tasks.isEmpty()) {
        return "# Отчёт за $dayLabel\n\nЗа $dayLabel время не учтено."
    }
    val totalSeconds = tasks.sumOf { todaySeconds(it, normalized, nowMillis) }
    val lines = mutableListOf(
        "# Отчёт за $dayLabel",
        "",
        "**Итого:** ${formatHm(totalSeconds)}",
        "",
    )
    tasks.forEachIndexed { index, task ->
        if (index > 0) {
            lines.add("")
        }
        lines.addAll(formatTaskSection(task, normalized, extended, nowMillis))
    }
    return lines.joinToString("\n")
}

private fun formatTaskSection(
    task: TaskDto,
    dateIso: String,
    extended: Boolean,
    nowMillis: Long,
): List<String> {
    val seconds = todaySeconds(task, dateIso, nowMillis)
    val lines = mutableListOf("## ${task.title} — ${formatHm(seconds)}")
    val result = task.result.trim()
    if (result.isNotEmpty()) {
        lines += listOf("", "**Результат:** $result")
    }
    if (!extended) {
        return lines
    }
    val description = task.description.trim()
    if (description.isNotEmpty()) {
        lines += listOf("", "### Описание", description)
    }
    val daySessions = task.sessions.filter { sessionLocalDate(it.startedAt) == dateIso }
    if (daySessions.isNotEmpty()) {
        lines += listOf(
            "",
            "### Сессии за день",
            "| Начало | Окончание | Длительность | Комментарий | Передано |",
            "| --- | --- | --- | --- | --- |",
        )
        for (session in daySessions) {
            val comment = session.comment.replace("|", "\\|").replace("\n", " ")
            val transferred = (session.bitrixRecordId ?: "").replace("|", "\\|")
            lines += "| ${formatTaskDateTime(session.startedAt) ?: "—"} | " +
                "${sessionEndedLabel(session)} | " +
                "${formatHm(sessionDurationSeconds(session, nowMillis))} | " +
                "$comment | $transferred |"
        }
    }
    return lines
}

private fun sessionEndedLabel(session: SessionDto): String {
    if (session.endedAt == null) {
        return "идёт"
    }
    return formatTaskDateTime(session.endedAt) ?: "—"
}

private fun sessionDurationSeconds(session: SessionDto, nowMillis: Long): Long {
    val start = parseInstant(session.startedAt) ?: return 0L
    val end = session.endedAt?.let(::parseInstant) ?: Instant.ofEpochMilli(nowMillis)
    return (end.epochSecond - start.epochSecond).coerceAtLeast(0)
}
