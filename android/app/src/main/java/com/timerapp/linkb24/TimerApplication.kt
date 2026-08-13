package com.timerapp.linkb24

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.timerapp.linkb24.data.AppPrefsRepository
import com.timerapp.linkb24.data.DEFAULT_UPDATE_GITHUB_REPO
import com.timerapp.linkb24.data.TaskRepository
import com.timerapp.linkb24.data.WebDavConfigRepository
import com.timerapp.linkb24.update.UpdateChecker
import com.timerapp.linkb24.webdav.WebDavNotificationHelper
import com.timerapp.linkb24.webdav.WebDavPeriodicMonitor
import com.timerapp.linkb24.webdav.WebDavReconnectMonitor
import com.timerapp.linkb24.webdav.WebDavSync
import com.timerapp.linkb24.webdav.WebDavWorkScheduler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class TimerApplication : Application() {
    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val webDavSync by lazy {
        WebDavSync(TaskRepository(this), WebDavConfigRepository(this))
    }
    private val webDavPeriodicMonitor by lazy {
        WebDavPeriodicMonitor(this)
    }
    private val webDavReconnectMonitor by lazy {
        WebDavReconnectMonitor(this, webDavSync)
    }
    private val appPrefsRepository by lazy { AppPrefsRepository(this) }

    override fun onCreate() {
        super.onCreate()
        WebDavWorkScheduler.schedule(this)
        webDavReconnectMonitor.start()
        ProcessLifecycleOwner.get().lifecycle.addObserver(
            object : DefaultLifecycleObserver {
                override fun onStart(owner: LifecycleOwner) {
                    webDavPeriodicMonitor.restart()
                    maybeCheckUpdates()
                }

                override fun onStop(owner: LifecycleOwner) {
                    webDavPeriodicMonitor.stop()
                    appScope.launch {
                        webDavSync.syncOnShutdown()
                    }
                }
            },
        )
    }

    fun restartWebDavPeriodicMonitor() {
        WebDavWorkScheduler.schedule(this)
        if (ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
            webDavPeriodicMonitor.restart()
        }
    }

    private fun maybeCheckUpdates() {
        if (!appPrefsRepository.shouldRunAutoCheck()) {
            return
        }
        appScope.launch {
            val prefs = appPrefsRepository.load()
            val result = UpdateChecker.checkForUpdate(
                dismissedVersion = prefs.dismissedUpdateVersion,
                respectDismissed = true,
                githubRepo = DEFAULT_UPDATE_GITHUB_REPO,
            )
            if (!result.ok) {
                appPrefsRepository.markCheckDone()
                return@launch
            }
            if (result.updateAvailable && result.latest != null) {
                WebDavNotificationHelper.showUpdateAvailable(
                    this@TimerApplication,
                    latestVersion = result.latest.version,
                    currentVersion = result.currentVersion,
                    htmlUrl = result.latest.htmlUrl,
                )
                appPrefsRepository.markCheckDone(dismissedVersion = result.latest.version)
            } else {
                appPrefsRepository.markCheckDone()
            }
        }
    }
}
