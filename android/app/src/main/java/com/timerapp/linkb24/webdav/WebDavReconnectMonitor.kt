package com.timerapp.linkb24.webdav

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Handler
import android.os.Looper
import com.timerapp.linkb24.data.TaskRepository
import com.timerapp.linkb24.data.WebDavConfigRepository
import java.util.concurrent.atomic.AtomicBoolean

class WebDavReconnectMonitor(
    private val context: Context,
    private val webDavSync: WebDavSync = WebDavSync(
        TaskRepository(context),
        WebDavConfigRepository(context),
    ),
    private val gate: WebDavReconnectGate = WebDavReconnectGate(),
) {
    private val connectivityManager =
        context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val mainHandler = Handler(Looper.getMainLooper())
    private val registered = AtomicBoolean(false)
    private val pushRunning = AtomicBoolean(false)
    private val debounceRunnable = Runnable { firePush() }

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            val busy = pushRunning.get()
            if (gate.onOnline(busy = busy)) {
                mainHandler.removeCallbacks(debounceRunnable)
                mainHandler.postDelayed(
                    debounceRunnable,
                    gateDebounceMs().coerceAtLeast(1L),
                )
            }
        }

        override fun onLost(network: Network) {
            mainHandler.removeCallbacks(debounceRunnable)
            gate.markOffline()
        }
    }

    fun start() {
        if (!registered.compareAndSet(false, true)) {
            return
        }
        if (!isOnline()) {
            gate.markOffline()
        }
        runCatching {
            connectivityManager.registerDefaultNetworkCallback(callback)
        }.onFailure {
            registered.set(false)
        }
    }

    fun stop() {
        if (!registered.compareAndSet(true, false)) {
            return
        }
        mainHandler.removeCallbacks(debounceRunnable)
        runCatching { connectivityManager.unregisterNetworkCallback(callback) }
    }

    private fun gateDebounceMs(): Long = (2.5 * 1000).toLong()

    private fun firePush() {
        if (pushRunning.get()) {
            gate.deferFireUntilIdle()
            return
        }
        if (!gate.beginPush()) {
            return
        }
        if (!pushRunning.compareAndSet(false, true)) {
            gate.deferFireUntilIdle()
            return
        }
        Thread {
            try {
                val outcome = webDavSync.syncOnReconnect()
                if (outcome.error.isNotBlank()) {
                    WebDavNotificationHelper.showSyncError(
                        context,
                        outcome.error,
                    )
                }
                // merge мог изменить data.json до ошибки загрузки — UI перечитывает
                WebDavDataChangedBus.notifyDataChanged()
            } finally {
                gate.endPush()
                pushRunning.set(false)
            }
        }.start()
    }

    private fun isOnline(): Boolean {
        val network = connectivityManager.activeNetwork ?: return false
        val caps = connectivityManager.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
