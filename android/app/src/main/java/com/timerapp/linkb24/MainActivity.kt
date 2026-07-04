package com.timerapp.linkb24

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import com.timerapp.linkb24.ui.RemoteChangePrompt
import com.timerapp.linkb24.ui.TimerAppExperimentApp
import com.timerapp.linkb24.webdav.WebDavNotificationHelper
import com.timerapp.linkb24.webdav.WebDavPromptBus

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleRemoteChangeIntent(intent)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(
                colorScheme = lightColorScheme(),
            ) {
                TimerAppExperimentApp()
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        handleRemoteChangeIntent(intent)
    }

    private fun handleRemoteChangeIntent(intent: android.content.Intent?) {
        val remoteHash = intent?.getStringExtra(WebDavNotificationHelper.EXTRA_REMOTE_HASH).orEmpty()
        if (remoteHash.isBlank()) {
            return
        }
        WebDavNotificationHelper.cancel(this)
        WebDavPromptBus.offer(RemoteChangePrompt(remoteHash = remoteHash))
    }
}
