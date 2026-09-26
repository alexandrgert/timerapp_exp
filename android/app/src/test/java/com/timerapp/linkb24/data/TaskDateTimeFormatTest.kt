package com.timerapp.linkb24.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.AfterClass
import org.junit.BeforeClass
import org.junit.Test
import java.util.TimeZone

class TaskDateTimeFormatTest {
    companion object {
        private lateinit var originalTimeZone: TimeZone

        @BeforeClass
        @JvmStatic
        fun useKnownDisplayTimeZone() {
            originalTimeZone = TimeZone.getDefault()
            // The formatter captures the device zone at class initialization.
            // Set it once for this class, before the first call, and restore it afterwards.
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"))
        }

        @AfterClass
        @JvmStatic
        fun restoreDisplayTimeZone() {
            TimeZone.setDefault(originalTimeZone)
        }
    }

    @Test
    fun formatTaskDateTime_convertsOffsetTimestampToDeviceZone() {
        val formatted = formatTaskDateTime("2026-06-28T20:31:00+03:00")
        assertEquals("28.06.2026 17:31", formatted)
    }

    @Test
    fun formatTaskDateTime_returnsNullForBlank() {
        assertNull(formatTaskDateTime(""))
        assertNull(formatTaskDateTime(null))
    }
}
