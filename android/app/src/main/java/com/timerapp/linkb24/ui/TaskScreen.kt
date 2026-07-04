package com.timerapp.linkb24.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.timerapp.linkb24.R
import com.timerapp.linkb24.data.TaskDto
import com.timerapp.linkb24.data.TaskStatus
import com.timerapp.linkb24.data.TaskViewFilter
import com.timerapp.linkb24.data.formatTaskDateTime
import com.timerapp.linkb24.data.isActive

private enum class AppScreen {
    Tasks,
    WebDavSettings,
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TimerAppExperimentApp(viewModel: TaskViewModel = viewModel()) {
    var screen by rememberSaveable { mutableStateOf(AppScreen.Tasks) }

    when (screen) {
        AppScreen.Tasks -> TaskListScreen(
            viewModel = viewModel,
            onOpenSettings = { screen = AppScreen.WebDavSettings },
        )
        AppScreen.WebDavSettings -> WebDavSettingsScreen(
            onBack = {
                screen = AppScreen.Tasks
                viewModel.reloadFromStorage()
            },
            onSyncComplete = viewModel::reloadFromStorage,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TaskListScreen(
    viewModel: TaskViewModel,
    onOpenSettings: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    uiState.remoteChangePrompt?.let {
        AlertDialog(
            onDismissRequest = viewModel::dismissRemotePull,
            title = { Text(stringResource(R.string.webdav_remote_change_title)) },
            text = { Text(stringResource(R.string.webdav_remote_change_message)) },
            confirmButton = {
                TextButton(onClick = viewModel::confirmRemotePull) {
                    Text(stringResource(R.string.webdav_remote_change_confirm))
                }
            },
            dismissButton = {
                TextButton(onClick = viewModel::dismissRemotePull) {
                    Text(stringResource(R.string.webdav_remote_change_later))
                }
            },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.app_name)) },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = stringResource(R.string.open_settings),
                        )
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilterChip(
                    selected = uiState.taskFilter == TaskViewFilter.TODAY,
                    onClick = { viewModel.onFilterChange(TaskViewFilter.TODAY) },
                    label = { Text(stringResource(R.string.filter_today)) },
                )
                FilterChip(
                    selected = uiState.taskFilter == TaskViewFilter.IN_PROGRESS,
                    onClick = { viewModel.onFilterChange(TaskViewFilter.IN_PROGRESS) },
                    label = { Text(stringResource(R.string.filter_in_progress)) },
                )
                FilterChip(
                    selected = uiState.taskFilter == TaskViewFilter.ALL,
                    onClick = { viewModel.onFilterChange(TaskViewFilter.ALL) },
                    label = { Text(stringResource(R.string.filter_all)) },
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilledTonalButton(
                    modifier = Modifier.weight(1f),
                    onClick = viewModel::pullWebDav,
                    enabled = !uiState.isWebDavSyncing && !uiState.isLoading,
                ) {
                    Text(stringResource(R.string.webdav_pull))
                }
                FilledTonalButton(
                    modifier = Modifier.weight(1f),
                    onClick = viewModel::pushWebDav,
                    enabled = !uiState.isWebDavSyncing && !uiState.isLoading,
                ) {
                    Text(stringResource(R.string.webdav_push))
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    modifier = Modifier.weight(1f),
                    value = uiState.newTaskTitle,
                    onValueChange = viewModel::onNewTaskTitleChange,
                    label = { Text("Новая задача") },
                    singleLine = true,
                )
                FilledTonalButton(onClick = viewModel::addTask) {
                    Text("Добавить")
                }
            }

            uiState.errorMessage?.let { message ->
                Text(message, color = MaterialTheme.colorScheme.error)
            }

            uiState.syncNotice?.let { message ->
                Text(message, color = MaterialTheme.colorScheme.primary)
            }

            if (uiState.isLoading) {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
            } else if (uiState.tasks.isEmpty()) {
                Text(
                    text = when (uiState.taskFilter) {
                        TaskViewFilter.TODAY -> stringResource(R.string.empty_tasks_today)
                        TaskViewFilter.IN_PROGRESS -> stringResource(R.string.empty_tasks_in_progress)
                        TaskViewFilter.ALL -> stringResource(R.string.empty_tasks_all)
                    },
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(uiState.tasks, key = { it.id }) { task ->
                        TaskRow(
                            task = task,
                            durationLabel = viewModel.durationLabel(task),
                            onToggle = { viewModel.toggleTimer(task.id) },
                            onComplete = { viewModel.completeTask(task.id) },
                            onResume = { viewModel.resumeTask(task.id) },
                            onDelete = { viewModel.deleteTask(task.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TaskRow(
    task: TaskDto,
    durationLabel: String,
    onToggle: () -> Unit,
    onComplete: () -> Unit,
    onResume: () -> Unit,
    onDelete: () -> Unit,
) {
    val isCompleted = task.status == TaskStatus.COMPLETED
    val titleColor = if (isCompleted) {
        MaterialTheme.colorScheme.onSurfaceVariant
    } else {
        MaterialTheme.colorScheme.onSurface
    }
    val createdLabel = formatTaskDateTime(task.createdAt)
    val completedLabel = formatTaskDateTime(task.completedAt)

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = task.title,
                style = MaterialTheme.typography.titleMedium.copy(
                    textDecoration = if (isCompleted) TextDecoration.LineThrough else null,
                ),
                color = titleColor,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = when {
                    isActive(task) -> "Идёт · $durationLabel"
                    task.status == TaskStatus.PAUSED -> "Пауза · $durationLabel"
                    else -> "Всего · $durationLabel"
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            createdLabel?.let { label ->
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = stringResource(R.string.task_created_at, label),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (isCompleted) {
                completedLabel?.let { label ->
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = stringResource(R.string.task_completed_at, label),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                if (!isCompleted) {
                    IconButton(onClick = onToggle) {
                        Icon(
                            imageVector = if (isActive(task)) Icons.Default.Stop else Icons.Default.PlayArrow,
                            contentDescription = if (isActive(task)) "Стоп" else "Старт",
                        )
                    }
                    IconButton(onClick = onComplete) {
                        Icon(Icons.Default.Check, contentDescription = "Завершить")
                    }
                } else {
                    IconButton(onClick = onResume) {
                        Icon(
                            imageVector = Icons.Default.PlayArrow,
                            contentDescription = stringResource(R.string.task_resume),
                        )
                    }
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, contentDescription = "Удалить")
                }
            }
        }
    }
}
