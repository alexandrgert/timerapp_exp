package com.timerapp.linkb24.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SettingsBundleTest {
    @Test
    fun exportParseRoundTrip() {
        val webdav = WebDavConfig(
            enabled = true,
            url = "https://cloud.example/dav/",
            username = "user",
            password = "secret",
        )
        val app = AppPrefs(checkUpdates = true, updateCheckIntervalDays = 2)
        val raw = SettingsBundle.exportJson(webdav, app)
        val parsed = SettingsBundle.parse(raw)
        assertTrue(parsed.ok)
        assertEquals("secret", parsed.webdav?.password)
        assertEquals(2, parsed.app?.updateCheckIntervalDays)
    }

    @Test
    fun rejectUnknownFormat() {
        val parsed = SettingsBundle.parse("""{"format":"other","version":1}""")
        assertFalse(parsed.ok)
    }

    @Test
    fun mergeKeepsLocalDeviceId() {
        val imported = WebDavConfig(url = "https://new/", username = "n", password = "p", deviceId = "other")
        val current = WebDavConfig(url = "https://old/", deviceId = "local-1", lastRemoteContentHash = "abc")
        val merged = SettingsBundle.mergeImportedWebDav(imported, current)
        assertEquals("local-1", merged.deviceId)
        assertEquals("https://new/", merged.url)
        assertEquals("", merged.lastError)
    }
}
