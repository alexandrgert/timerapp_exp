package com.timerapp.linkb24.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.timerapp.linkb24.data.TaskDto
import com.timerapp.linkb24.sync.SyncV2
import kotlinx.serialization.json.JsonElement

@Composable
internal fun SyncConflictControls(
    conflicts: List<SyncV2.Conflict>, concurrentTasks: List<TaskDto>,
    onResolve: (SyncV2.Conflict,JsonElement)->Unit, onKeepTimer: (String,String)->Unit,
) {
    var opened by remember { mutableStateOf(false) }
    if(conflicts.isEmpty() && concurrentTasks.isEmpty())return
    TextButton(onClick={opened=true}) { Text("Разобрать конфликты синхронизации (${conflicts.size + if(concurrentTasks.isNotEmpty()) 1 else 0})") }
    if(opened)AlertDialog(onDismissRequest={opened=false},title={Text("Конфликты синхронизации")},
        text={Column(Modifier.heightIn(max=420.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            conflicts.firstOrNull()?.let { conflict ->
                Text("${conflict.entity.drop(1).joinToString(" / ")} · ${conflict.field}")
                Text("Выберите сохранённый вариант. Остальные изменения останутся.")
                conflict.candidates.forEach { candidate -> TextButton(onClick={onResolve(conflict,candidate.value)}) { Text(if(conflict.field=="\$alive") if(candidate.value.toString()=="true") "Сохранить запись" else "Удалить запись" else candidate.value.toString()) } }
            }
            if(concurrentTasks.isNotEmpty()) {
                Text("Одновременно запущено несколько сессий. Какую оставить работающей? Остальные завершатся текущим временем.")
                concurrentTasks.forEach { task -> task.sessions.filter { it.endedAt==null }.forEach { session ->
                    TextButton(onClick={onKeepTimer(task.id,session.id)}) { Text("${task.title} · ${session.startedAt}") }
                } }
            }
        }},confirmButton={TextButton(onClick={opened=false}) { Text("Закрыть") }})
}
