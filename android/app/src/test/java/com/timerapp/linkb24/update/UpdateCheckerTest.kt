package com.timerapp.linkb24.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdateCheckerTest {
    @Test
    fun normalizeAndCompare() {
        assertEquals("0.9.2", UpdateChecker.normalizeVersion("v0.9.2"))
        assertTrue(UpdateChecker.isNewer("0.9.1", "0.9.2"))
        assertFalse(UpdateChecker.isNewer("0.9.2", "0.9.2"))
    }

    @Test
    fun parseLatestRelease() {
        val release = UpdateChecker.parseLatestRelease(
            """{"tag_name":"v1.2.0","html_url":"https://example/release"}""",
        )
        assertEquals("1.2.0", release.version)
    }

    @Test
    fun respectDismissed() {
        val latest = LatestRelease("v0.9.5", "0.9.5", "https://x")
        val dismissed = UpdateChecker.checkForUpdate(
            currentVersion = "0.9.1",
            dismissedVersion = "0.9.5",
            respectDismissed = true,
            fetch = { latest },
        )
        assertTrue(dismissed.ok)
        assertFalse(dismissed.updateAvailable)
        val manual = UpdateChecker.checkForUpdate(
            currentVersion = "0.9.1",
            dismissedVersion = "0.9.5",
            respectDismissed = false,
            fetch = { latest },
        )
        assertTrue(manual.updateAvailable)
    }

    @Test
    fun latestReleaseApiUrlUsesRepo() {
        assertEquals(
            "https://api.github.com/repos/alexandrgert/timer-app/releases/latest",
            UpdateChecker.latestReleaseApiUrl("alexandrgert/timer-app"),
        )
    }
}
