package com.timerapp.linkb24.webdav

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.timerapp.linkb24.MainActivity
import com.timerapp.linkb24.R
import com.timerapp.linkb24.ui.RemoteChangePrompt

object WebDavNotificationHelper {
    const val CHANNEL_ID = "webdav_remote_changes"
    const val NOTIFICATION_ID = 4101

    const val ACTION_CONFIRM = "com.timerapp.exp.webdav.ACTION_CONFIRM"
    const val ACTION_LATER = "com.timerapp.exp.webdav.ACTION_LATER"
    const val EXTRA_REMOTE_HASH = "remote_hash"

    fun showRemoteChange(context: Context, prompt: RemoteChangePrompt) {
        ensureChannel(context)
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(context.getString(R.string.webdav_remote_change_title))
            .setContentText(context.getString(R.string.webdav_remote_change_message))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openAppIntent(context, prompt.remoteHash))
            .addAction(
                0,
                context.getString(R.string.webdav_remote_change_confirm),
                actionIntent(context, ACTION_CONFIRM, prompt.remoteHash),
            )
            .addAction(
                0,
                context.getString(R.string.webdav_remote_change_later),
                actionIntent(context, ACTION_LATER, prompt.remoteHash),
            )
            .build()
        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification)
    }

    fun cancel(context: Context) {
        NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID)
    }

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(CHANNEL_ID) != null) {
            return
        }
        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.webdav_remote_change_channel),
            NotificationManager.IMPORTANCE_HIGH,
        )
        manager.createNotificationChannel(channel)
    }

    private fun openAppIntent(context: Context, remoteHash: String): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_REMOTE_HASH, remoteHash)
        }
        return PendingIntent.getActivity(
            context,
            0,
            intent,
            pendingIntentFlags(),
        )
    }

    private fun actionIntent(context: Context, action: String, remoteHash: String): PendingIntent {
        val intent = Intent(context, WebDavRemoteActionReceiver::class.java).apply {
            this.action = action
            putExtra(EXTRA_REMOTE_HASH, remoteHash)
        }
        val requestCode = when (action) {
            ACTION_CONFIRM -> 1
            ACTION_LATER -> 2
            else -> 3
        }
        return PendingIntent.getBroadcast(
            context,
            requestCode,
            intent,
            pendingIntentFlags(),
        )
    }

    private fun pendingIntentFlags(): Int {
        return PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    }
}
