package com.timerapp.linkb24.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import com.timerapp.linkb24.data.FocusTimerDto
import com.timerapp.linkb24.data.TaskDto
import com.timerapp.linkb24.data.formatDuration
import com.timerapp.linkb24.data.parseInstant

@Composable
fun FocusStartDialog(
    task: TaskDto,
    selectedMinutes: Int,
    needsPriority: Boolean,
    onDismiss: () -> Unit,
    onStart: (Int, Int?, (String?) -> Unit) -> Unit,
) {
    var minutes by rememberSaveable(task.id) { mutableStateOf(selectedMinutes.coerceIn(1, 180).toString()) }
    var priority by rememberSaveable(task.id) { mutableStateOf<Int?>(null) }
    var saving by remember(task.id) { mutableStateOf(false) }
    var error by rememberSaveable(task.id) { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val notifications = NotificationManagerCompat.from(context).areNotificationsEnabled()
    var pendingMinutes by rememberSaveable(task.id) { mutableStateOf<Int?>(null) }
    var pendingPriority by rememberSaveable(task.id) { mutableStateOf<Int?>(null) }
    val commitStart: (Int, Int?) -> Unit = { value, selectedPriority ->
        saving = true
        onStart(value, selectedPriority) { problem ->
            saving = false
            if (problem == null) onDismiss() else error = problem
        }
    }
    val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        // A declined notification permission never prevents tracking time.
        pendingMinutes?.let { value ->
            pendingMinutes = null
            commitStart(value, pendingPriority)
        }
    }
    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        title = { Text("Концентрация: ${task.title}") },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = minutes, onValueChange = { minutes = it; error = null },
                    label = { Text("Минуты (1–180)") }, enabled = !saving, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                if (needsPriority) {
                    Text("Приоритет")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        (1..4).forEach { value ->
                            FilterChip(selected = priority == value, onClick = { priority = value },
                                enabled = !saving, label = { Text(value.toString()) })
                        }
                    }
                }
                Text("Текущая задача будет поставлена на паузу. По окончании эта сессия остановится.")
                if (!notifications) Text("Уведомления выключены: звукового напоминания не будет.")
                Text("В фоне Android может задержать уведомление. Время сессии ограничено таймером.",
                    style = MaterialTheme.typography.bodySmall)
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(enabled = !saving, onClick = {
                val value = minutes.toIntOrNull()
                if (value == null || value !in 1..180) error = "Укажите от 1 до 180 минут."
                else if (needsPriority && priority == null) error = "Выберите приоритет."
                else {
                    if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context,
                            Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                        saving = true
                        pendingMinutes = value
                        pendingPriority = priority
                        notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else commitStart(value, priority)
                }
            }) { Text(if (saving) "Запуск…" else "Начать") }
        },
        dismissButton = { TextButton(enabled = !saving, onClick = onDismiss) { Text("Отмена") } },
    )
}

@Composable
fun ActiveFocusPanel(focus: FocusTimerDto, taskTitle: String, nowMillis: Long, onStop: () -> Unit) {
    val end = focus.endsAt?.let(::parseInstant) ?: return
    val remaining = ((end.toEpochMilli() - nowMillis + 999L) / 1000L).coerceAtLeast(0)
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text("Концентрация · $taskTitle", style = MaterialTheme.typography.titleSmall)
            if (!NotificationManagerCompat.from(LocalContext.current).areNotificationsEnabled()) {
                Text("Уведомления выключены: напоминание о завершении не появится.",
                    style = MaterialTheme.typography.bodySmall)
            }
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(formatDuration(remaining), style = MaterialTheme.typography.headlineSmall)
                TextButton(onClick = onStop) { Text("Остановить концентрацию") }
            }
        }
    }
}
