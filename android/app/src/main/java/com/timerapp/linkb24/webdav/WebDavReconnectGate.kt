package com.timerapp.linkb24.webdav

/**
 * Edge offline→online gate for deferred WebDAV push.
 */
class WebDavReconnectGate(
    private val debounceSeconds: Double = 2.5,
    private val cooldownSeconds: Double = 60.0,
) {
    @Volatile
    var wasOffline: Boolean = false
        private set

    @Volatile
    var syncInProgress: Boolean = false

    @Volatile
    var deferredWhileBusy: Boolean = false
        private set

    @Volatile
    private var lastPushMonotonic: Double = 0.0

    @Volatile
    private var pendingOnlineAt: Double? = null

    fun markOffline() {
        wasOffline = true
        pendingOnlineAt = null
        deferredWhileBusy = false
    }

    fun onOnline(busy: Boolean = false, nowSeconds: Double = monotonicNow()): Boolean {
        if (!wasOffline && !deferredWhileBusy) {
            return false
        }
        if (busy || syncInProgress) {
            if (wasOffline) {
                deferredWhileBusy = true
            }
            return false
        }
        if (lastPushMonotonic > 0 && (nowSeconds - lastPushMonotonic) < cooldownSeconds) {
            deferredWhileBusy = false
            return false
        }
        deferredWhileBusy = false
        pendingOnlineAt = nowSeconds
        if (!wasOffline) {
            wasOffline = true
        }
        return true
    }

    fun onBusyFinished(nowSeconds: Double = monotonicNow()): Boolean {
        if (!deferredWhileBusy) {
            return false
        }
        return onOnline(busy = false, nowSeconds = nowSeconds)
    }

    /** Совместимость: online без busy. */
    fun markOnline(nowSeconds: Double = monotonicNow()): Boolean =
        onOnline(busy = false, nowSeconds = nowSeconds)

    fun shouldFirePush(nowSeconds: Double = monotonicNow()): Boolean {
        val pending = pendingOnlineAt ?: return false
        if (!wasOffline || syncInProgress) {
            return false
        }
        if (nowSeconds - pending < debounceSeconds) {
            return false
        }
        if (lastPushMonotonic > 0 && (nowSeconds - lastPushMonotonic) < cooldownSeconds) {
            return false
        }
        return true
    }

    fun beginPush(nowSeconds: Double = monotonicNow()): Boolean {
        if (!shouldFirePush(nowSeconds)) {
            return false
        }
        syncInProgress = true
        wasOffline = false
        pendingOnlineAt = null
        deferredWhileBusy = false
        return true
    }

    fun deferFireUntilIdle() {
        wasOffline = true
        pendingOnlineAt = null
        deferredWhileBusy = true
        syncInProgress = false
    }

    fun endPush(nowSeconds: Double = monotonicNow()) {
        syncInProgress = false
        lastPushMonotonic = nowSeconds
    }

    companion object {
        fun monotonicNow(): Double = System.nanoTime() / 1_000_000_000.0
    }
}
