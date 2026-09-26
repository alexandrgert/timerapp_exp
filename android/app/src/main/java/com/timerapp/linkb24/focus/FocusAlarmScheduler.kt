package com.timerapp.linkb24.focus

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.timerapp.linkb24.MainActivity
import com.timerapp.linkb24.R
import com.timerapp.linkb24.data.AppDataDto
import com.timerapp.linkb24.data.AppJson
import com.timerapp.linkb24.data.TaskStatus
import com.timerapp.linkb24.data.parseInstant
import java.io.File

/** The alarm only notifies. Repository reconciliation owns data writes and exact session cutoff. */
object FocusAlarmScheduler {
    private const val REQUEST = 4201
    private const val CHANNEL = "focus_completion"
    private const val EXTRA = "focus_deadline"

    @Volatile var lastError: String? = null
        private set

    fun update(context: Context, data: AppDataDto) {
        lastError = runCatching { updateAlarm(context, data) }.exceptionOrNull()?.let {
            if (data.ui.focusTimer.endsAt != null) "Не удалось установить фоновое напоминание. Отсчёт сохранён; откройте приложение для проверки." else null
        }
    }

    private fun updateAlarm(context: Context, data: AppDataDto) {
        val focus = data.ui.focusTimer
        val end = focus.endsAt?.let(::parseInstant)
        val task = data.tasks.firstOrNull { it.id == focus.sessionTaskId }
        val manager = context.getSystemService(AlarmManager::class.java)
        val intent = Intent(context, FocusAlarmReceiver::class.java).putExtra(EXTRA, focus.endsAt)
        val pending = PendingIntent.getBroadcast(context, REQUEST, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        if (end == null || task == null || task.status != TaskStatus.RUNNING || task.sessions.none { it.endedAt == null }) {
            manager.cancel(pending)
            val completedTask = context.getSharedPreferences("focus_notifications", Context.MODE_PRIVATE)
                .getString("last_completed_task", null)
            if (completedTask != null && data.tasks.none { it.id == completedTask }) {
                context.getSystemService(NotificationManager::class.java).cancel(REQUEST)
            }
            return
        }
        if (end.toEpochMilli() <= System.currentTimeMillis()) {
            manager.cancel(pending)
            notifyOnce(context, "${task.id}|${focus.endsAt}", task.title)
        } else {
            context.getSystemService(NotificationManager::class.java).cancel(REQUEST)
            manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, end.toEpochMilli(), pending)
        }
    }

    fun onAlarm(context: Context, intent: Intent) {
        // Read only: no second read/modify/write actor competing with UI/WebDAV.
        val data = runCatching {
            AppJson.decodeFromString(AppDataDto.serializer(), File(context.filesDir, "data.json").readText())
        }.getOrNull() ?: return
        if (intent.getStringExtra(EXTRA) != data.ui.focusTimer.endsAt) return
        update(context, data)
    }

    private fun notifyOnce(context: Context, token: String, title: String) {
        val prefs = context.getSharedPreferences("focus_notifications", Context.MODE_PRIVATE)
        if (prefs.getString("last_completed", null) == token) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Завершение концентрации", NotificationManager.IMPORTANCE_HIGH))
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return
        val open = PendingIntent.getActivity(context, REQUEST, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        try {
            manager.notify(REQUEST, NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle("Концентрация завершена")
                .setContentText(title)
                .setAutoCancel(true)
                .setContentIntent(open)
                .build())
            prefs.edit().putString("last_completed", token).putString("last_completed_task", token.substringBefore("|")).apply()
        } catch (_: SecurityException) {
            // Permission may have been revoked between the check and notify.
        }
    }
}

class FocusAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        FocusAlarmScheduler.onAlarm(context, intent)
    }
}
