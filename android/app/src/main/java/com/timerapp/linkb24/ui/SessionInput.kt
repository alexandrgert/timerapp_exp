package com.timerapp.linkb24.ui

import com.timerapp.linkb24.data.parseInstant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

fun sessionTimeFields(timestamp: String, zone: ZoneId = ZoneId.systemDefault()): Pair<String, String> {
    val date = requireNotNull(parseInstant(timestamp)) { "Некорректная дата сессии." }.atZone(zone)
    return date.toLocalDate().toString() to date.toLocalTime().toString()
}

fun sessionTimestamp(date: String, time: String, original: String? = null, zone: ZoneId = ZoneId.systemDefault()): String {
    if (original != null && sessionTimeFields(original, zone) == (date to time)) return original
    val local = try {
        LocalDateTime.of(LocalDate.parse(date, DateTimeFormatter.ISO_LOCAL_DATE),
            LocalTime.parse(time, DateTimeFormatter.ISO_LOCAL_TIME))
    } catch (_: java.time.DateTimeException) {
        throw IllegalArgumentException("Введите действительную дату ГГГГ-ММ-ДД и время ЧЧ:ММ (можно с секундами).")
    }
    val offsets = zone.rules.getValidOffsets(local)
    require(offsets.isNotEmpty()) { "Это время отсутствует в часовом поясе $zone из-за перевода часов." }
    // Keep the original offset during the repeated hour, if still valid.
    val originalOffset = original?.let(::parseInstant)?.atZone(zone)?.offset
    val offset = originalOffset?.takeIf { it in offsets } ?: offsets.first()
    return local.atOffset(offset).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
}
