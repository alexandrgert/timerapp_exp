package com.timerapp.linkb24.webdav

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.Rule
import java.io.File

class WebDavSyncLogTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun appendAndFormat() {
        val log = WebDavSyncLog(File(tempFolder.root, "webdav-sync.log"))
        log.append("push", uploadedTasks = 3, downloadedTasks = 2)
        log.append("reconnect_push", uploadedTasks = 1, ok = false, error = "timeout")
        val text = log.formatForDisplay()
        assertTrue(text.contains("↑3"))
        assertTrue(text.contains("ОШИБКА: timeout"))
        assertEquals(2, log.readEntries().size)
    }

    @Test
    fun countTasksInPayload() {
        assertEquals(2, WebDavSyncLog.countTasksInPayload("""{"tasks":[{},{}]}""".toByteArray()))
        assertEquals(0, WebDavSyncLog.countTasksInPayload("{}".toByteArray()))
    }
}

class WebDavReconnectGateTest {
    @Test
    fun edgeDebounceAndCooldown() {
        val gate = WebDavReconnectGate(debounceSeconds = 2.5, cooldownSeconds = 60.0)
        assertFalse(gate.markOnline(nowSeconds = 100.0))
        gate.markOffline()
        assertTrue(gate.markOnline(nowSeconds = 101.0))
        assertFalse(gate.shouldFirePush(nowSeconds = 102.0))
        assertTrue(gate.shouldFirePush(nowSeconds = 104.0))
        assertTrue(gate.beginPush(nowSeconds = 104.0))
        gate.endPush(nowSeconds = 104.0)
        gate.markOffline()
        assertFalse(gate.markOnline(nowSeconds = 120.0))
        assertTrue(gate.markOnline(nowSeconds = 170.0))
    }

    @Test
    fun defersWhileBusy() {
        val gate = WebDavReconnectGate(debounceSeconds = 2.5, cooldownSeconds = 60.0)
        gate.markOffline()
        assertFalse(gate.onOnline(busy = true, nowSeconds = 100.0))
        assertTrue(gate.deferredWhileBusy)
        assertTrue(gate.wasOffline)
        assertTrue(gate.onBusyFinished(nowSeconds = 101.0))
        assertTrue(gate.shouldFirePush(nowSeconds = 104.0))
        gate.deferFireUntilIdle()
        assertTrue(gate.deferredWhileBusy)
        assertFalse(gate.beginPush(nowSeconds = 110.0))
        assertTrue(gate.onBusyFinished(nowSeconds = 111.0))
        assertTrue(gate.beginPush(nowSeconds = 114.0))
        gate.endPush(nowSeconds = 114.0)
    }
}
