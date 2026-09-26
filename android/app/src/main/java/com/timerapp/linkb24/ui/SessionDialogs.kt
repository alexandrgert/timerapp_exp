package com.timerapp.linkb24.ui

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import com.timerapp.linkb24.data.SessionDto
import com.timerapp.linkb24.data.formatDuration
import com.timerapp.linkb24.data.parseInstant
import java.time.LocalDate
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.Locale

internal const val SYNC_EDIT_WARNING = "При синхронизации старая длительность или комментарий могут восстановиться. Исправление применяется локально."
internal const val SYNC_DELETE_WARNING = "При синхронизации удалённая запись может восстановиться с другого устройства."
internal const val BITRIX_EDIT_WARNING = "Время уже передано в Битрикс24. Эта правка изменит только локальную запись, без изменения или повторной отправки в Битрикс24."
internal const val BITRIX_DELETE_WARNING = "Переданная запись времени в Битрикс24 не будет удалена."

@Composable
internal fun SessionEditorDialog(
    session: SessionDto?,
    syncConfigured: Boolean,
    onDismiss: () -> Unit,
    onSave: (String, String?, String, (String?) -> Unit) -> Unit,
) {
    val initialEnd = remember { OffsetDateTime.now().withNano(0) }
    val initialStart = remember { session?.startedAt ?: initialEnd.minusHours(1).toString() }
    val initialFinish = remember { session?.endedAt ?: initialEnd.toString() }
    val startFields = remember { runCatching { sessionTimeFields(initialStart) }.getOrElse { "" to "" } }
    val endFields = remember { runCatching { sessionTimeFields(initialFinish) }.getOrElse { "" to "" } }
    var startDate by rememberSaveable { mutableStateOf(startFields.first) }
    var startTime by rememberSaveable { mutableStateOf(startFields.second) }
    var endDate by rememberSaveable { mutableStateOf(endFields.first) }
    var endTime by rememberSaveable { mutableStateOf(endFields.second) }
    var running by rememberSaveable { mutableStateOf(session != null && session.endedAt == null) }
    var comment by rememberSaveable { mutableStateOf(session?.comment.orEmpty()) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val parsed = runCatching {
        val start = sessionTimestamp(startDate, startTime, session?.startedAt)
        val end = if (running) null else sessionTimestamp(endDate, endTime, session?.endedAt)
        if (end != null) require(parseInstant(end)!!.isAfter(parseInstant(start))) { "Окончание должно быть позже начала." }
        start to end
    }
    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        properties = DialogProperties(dismissOnBackPress = !saving, dismissOnClickOutside = !saving),
        title = { Text(if (session == null) "Добавить сессию" else "Редактировать сессию") },
        text = {
            Column(Modifier.fillMaxWidth().heightIn(max = 440.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Часовой пояс: ${ZoneId.systemDefault().id}", style = MaterialTheme.typography.bodySmall)
                SessionDateTimeFields("Начало", "start", startDate, startTime, !saving,
                    { startDate = it; error = null }, { startTime = it; error = null })
                if (session != null && session.endedAt == null) {
                    Row {
                        Checkbox(checked = running, enabled = !saving, onCheckedChange = { running = it; error = null })
                        Text("Сессия продолжается", Modifier.padding(top = 12.dp))
                    }
                }
                if (!running) SessionDateTimeFields("Окончание", "end", endDate, endTime, !saving,
                    { endDate = it; error = null }, { endTime = it; error = null })
                parsed.getOrNull()?.let { (start, end) ->
                    if (end != null) Text("Длительность: ${formatDuration(java.time.Duration.between(parseInstant(start), parseInstant(end)).seconds)}")
                }
                OutlinedTextField(value = comment, onValueChange = { comment = it }, enabled = !saving,
                    label = { Text("Комментарий") }, modifier = Modifier.fillMaxWidth().testTag("session-comment"), minLines = 2)
                if (!session?.bitrixRecordId.isNullOrBlank()) Text(BITRIX_EDIT_WARNING, style = MaterialTheme.typography.bodySmall)
                if (session != null && syncConfigured) Text(SYNC_EDIT_WARNING, style = MaterialTheme.typography.bodySmall)
                (error ?: parsed.exceptionOrNull()?.message)?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(enabled = !saving, modifier = Modifier.testTag("session-save"), onClick = {
                parsed.fold(onSuccess = { (start, end) ->
                    saving = true
                    onSave(start, end, comment) { failure ->
                        saving = false
                        if (failure == null) onDismiss() else error = failure
                    }
                }, onFailure = { error = it.message })
            }) { Text(if (saving) "Сохранение…" else "Сохранить") }
        },
        dismissButton = { TextButton(enabled = !saving, onClick = onDismiss) { Text("Отмена") } },
    )
}

@Composable
private fun SessionDateTimeFields(
    title: String, tag: String, date: String, time: String, enabled: Boolean,
    onDate: (String) -> Unit, onTime: (String) -> Unit,
) {
    val context = LocalContext.current
    Text(title, style = MaterialTheme.typography.titleSmall)
    OutlinedTextField(value = date, onValueChange = onDate, enabled = enabled, singleLine = true,
        label = { Text("Дата (ГГГГ-ММ-ДД)") }, modifier = Modifier.fillMaxWidth().testTag("$tag-date"),
        trailingIcon = {
            TextButton(enabled = enabled, onClick = {
                val selected = runCatching { LocalDate.parse(date) }.getOrElse { LocalDate.now() }
                DatePickerDialog(context, { _, year, month, day -> onDate(LocalDate.of(year, month + 1, day).toString()) },
                    selected.year, selected.monthValue - 1, selected.dayOfMonth).show()
            }) { Text("Выбрать") }
        })
    OutlinedTextField(value = time, onValueChange = onTime, enabled = enabled, singleLine = true,
        label = { Text("Время (ЧЧ:ММ[:СС])") }, modifier = Modifier.fillMaxWidth().testTag("$tag-time"),
        trailingIcon = {
            TextButton(enabled = enabled, onClick = {
                val selected = runCatching { LocalTime.parse(time) }.getOrElse { LocalTime.now() }
                TimePickerDialog(context, { _, hour, minute -> onTime(String.format(Locale.ROOT, "%02d:%02d", hour, minute)) },
                    selected.hour, selected.minute, true).show()
            }) { Text("Выбрать") }
        })
}

@Composable
internal fun DeleteRecordDialog(
    title: String, message: String, syncConfigured: Boolean, transferred: Boolean,
    onDismiss: () -> Unit, onDelete: ((String?) -> Unit) -> Unit,
) {
    var saving by remember { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        properties = DialogProperties(dismissOnBackPress = !saving, dismissOnClickOutside = !saving),
        title = { Text(title) },
        text = { Column(Modifier.heightIn(max = 400.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(message)
            if (syncConfigured) Text(SYNC_DELETE_WARNING)
            if (transferred) Text(BITRIX_DELETE_WARNING)
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        } },
        confirmButton = { TextButton(enabled = !saving, modifier = Modifier.testTag("delete-confirm"), onClick = {
            saving = true
            onDelete { failure -> saving = false; if (failure == null) onDismiss() else error = failure }
        }) { Text(if (saving) "Удаление…" else "Удалить") } },
        dismissButton = { TextButton(enabled = !saving, onClick = onDismiss) { Text("Отмена") } },
    )
}
