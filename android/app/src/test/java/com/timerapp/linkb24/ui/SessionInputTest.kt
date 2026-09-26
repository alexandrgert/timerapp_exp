package com.timerapp.linkb24.ui

import org.junit.Assert.*
import org.junit.Test
import java.time.ZoneId

class SessionInputTest {
    @Test fun comment_only_edit_keeps_original_timestamp_verbatim() {
        val original = "2026-08-12T23:30:12.123456789+03:00"
        val zone = ZoneId.of("UTC")
        val fields = sessionTimeFields(original, zone)
        assertEquals(original, sessionTimestamp(fields.first, fields.second, original, zone))
    }

    @Test fun dates_are_strict_and_allow_midnight_and_seconds() {
        assertEquals("2024-02-29T00:00:00Z", sessionTimestamp("2024-02-29", "00:00", zone = ZoneId.of("UTC")))
        for ((date, time) in listOf("2026-02-29" to "10:00", "2026-04-31" to "10:00", "2026-01-01" to "24:00")) {
            try { sessionTimestamp(date, time); fail("Expected invalid date/time") } catch (_: IllegalArgumentException) { }
        }
    }

    @Test fun nonexistent_dst_time_is_rejected() {
        try { sessionTimestamp("2026-03-29", "02:30", zone = ZoneId.of("Europe/Berlin")); fail("Expected DST validation") }
        catch (_: IllegalArgumentException) { }
    }
}
