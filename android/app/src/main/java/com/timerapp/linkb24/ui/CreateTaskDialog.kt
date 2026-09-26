package com.timerapp.linkb24.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import com.timerapp.linkb24.voice.VoiceInputButton

@Composable
internal fun CreateTaskDialog(
    onDismiss: () -> Unit,
    onSave: (String, String, (String?) -> Unit) -> Unit,
) {
    var title by rememberSaveable { mutableStateOf("") }
    var description by rememberSaveable { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        properties = DialogProperties(dismissOnBackPress = !saving, dismissOnClickOutside = !saving),
        title = { Text("Новая задача") },
        text = { Column(Modifier.fillMaxWidth().heightIn(max = 420.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(value = title, onValueChange = { title = it; error = null },
                label = { Text("Название") }, singleLine = true, enabled = !saving,
                modifier = Modifier.fillMaxWidth().testTag("create-title"),
                trailingIcon = { VoiceInputButton("название задачи", title, !saving) { title = it; error = null } })
            OutlinedTextField(value = description, onValueChange = { description = it },
                label = { Text("Описание") }, minLines = 3, enabled = !saving,
                modifier = Modifier.fillMaxWidth().testTag("create-description"),
                trailingIcon = { VoiceInputButton("описание задачи", description, !saving) { description = it } })
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        } },
        confirmButton = { TextButton(enabled = !saving, onClick = {
            if (title.isBlank()) error = "Введите название задачи."
            else {
                saving = true
                onSave(title, description) { failure ->
                    saving = false
                    if (failure == null) onDismiss() else error = failure
                }
            }
        }) { Text(if (saving) "Сохранение…" else "Создать") } },
        dismissButton = { TextButton(enabled = !saving, onClick = onDismiss) { Text("Отмена") } },
    )
}
