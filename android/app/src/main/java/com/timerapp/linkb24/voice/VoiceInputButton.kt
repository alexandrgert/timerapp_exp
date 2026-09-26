package com.timerapp.linkb24.voice

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.util.Locale

@Composable
internal fun VoiceInputButton(
    fieldName: String,
    currentText: String,
    enabled: Boolean = true,
    onText: (String) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    val latestText by rememberUpdatedState(currentText)
    val latestOnText by rememberUpdatedState(onText)
    IconButton(enabled = enabled, onClick = { open = true }) {
        Icon(Icons.Default.Mic, contentDescription = "Голосом: $fieldName")
    }
    if (open) VoiceInputDialog(onDismiss = { open = false }, onApply = { recognized ->
        latestOnText(appendDictation(latestText, recognized))
        open = false
    })
}

@Composable
private fun VoiceInputDialog(onDismiss: () -> Unit, onApply: (String) -> Unit) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val controller = remember { VoiceInputController(context.applicationContext) }
    val state by controller.state.collectAsState()
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        if (allowed && owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) controller.start()
        else if (!allowed) controller.permissionDenied()
    }
    DisposableEffect(controller, owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) controller.stop()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); controller.close() }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Диктовка офлайн") },
        text = {
            Column(Modifier.fillMaxWidth().heightIn(max = 420.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                when {
                    state.checking -> { CircularProgressIndicator(); Text("Проверка голосовой модели…") }
                    state.downloading -> {
                        Text(if (state.unpacking) "Распаковка модели…" else
                            "Скачано ${megabytes(state.downloadedBytes)} из ${megabytes(RussianVoiceModel.ARCHIVE_BYTES)} МБ")
                        if (state.unpacking) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                        else LinearProgressIndicator(progress = { (state.downloadedBytes.toFloat() / RussianVoiceModel.ARCHIVE_BYTES).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
                        TextButton(onClick = controller::cancelDownload) { Text("Отменить загрузку") }
                    }
                    !state.modelReady -> {
                        Text("Для русского языка нужно один раз скачать модель: 46,2 МБ, после распаковки 91,3 МБ. Для установки нужно 155 МБ свободного места. Затем диктовка работает без интернета; звук не отправляется на сервер.")
                        FilledTonalButton(onClick = controller::download) { Text("Скачать модель") }
                    }
                    else -> {
                        Text(when {
                            state.stopping -> "Остановка…"
                            state.loading -> "Загрузка модели в память…"
                            state.recording -> "Слушаю. Нажмите «Остановить», когда закончите."
                            else -> "Русский язык · без интернета"
                        })
                        OutlinedTextField(value = appendDictation(state.text, state.partial), onValueChange = controller::editText,
                            readOnly = state.microphoneBusy, label = { Text("Распознанный текст") }, minLines = 3,
                            modifier = Modifier.fillMaxWidth())
                        if (state.microphoneBusy) {
                            TextButton(enabled = !state.stopping, onClick = controller::stop) { Text("Остановить") }
                        } else {
                            FilledTonalButton(onClick = {
                                if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) controller.start()
                                else permission.launch(Manifest.permission.RECORD_AUDIO)
                            }) { Text(if (state.text.isBlank()) "Начать диктовку" else "Продолжить диктовку") }
                        }
                    }
                }
                state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                if (state.error != null && ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    TextButton(onClick = {
                        context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}")))
                    }) { Text("Разрешения приложения") }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = state.text.isNotBlank() && !state.microphoneBusy && !state.downloading,
                onClick = { onApply(state.text) }) { Text("Добавить текст") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
    )
}

private fun megabytes(bytes: Long): String = String.format(Locale.forLanguageTag("ru"), "%.1f", bytes / 1_000_000.0)
