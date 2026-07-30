package com.timerapp.linkb24.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.timerapp.linkb24.R
import com.timerapp.linkb24.data.SessionDto
import com.timerapp.linkb24.data.TaskDto
import com.timerapp.linkb24.data.TaskStatus
import com.timerapp.linkb24.data.TaskViewFilter
import com.timerapp.linkb24.data.formatDuration
import com.timerapp.linkb24.data.formatTaskDateTime
import com.timerapp.linkb24.data.isActive
import com.timerapp.linkb24.data.parseInstant
import com.timerapp.linkb24.data.parseIsoDateOrNull
import com.timerapp.linkb24.data.taskPriority
import com.timerapp.linkb24.data.todayIsoDate
import java.time.Instant

private enum class AppScreen {
    Tasks,
    WebDavSettings,
}

private data class PriorityStartRequest(
    val taskId: String,
    val resumeComment: String? = null,
)

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
    val context = LocalContext.current
    val isSelectionMode = uiState.selectedTaskIds.isNotEmpty()
    var completeTaskId by remember { mutableStateOf<String?>(null) }
    var resumeTaskId by remember { mutableStateOf<String?>(null) }
    var historyTaskId by remember { mutableStateOf<String?>(null) }
    var editTaskId by remember { mutableStateOf<String?>(null) }
    var priorityStartRequest by remember { mutableStateOf<PriorityStartRequest?>(null) }
    var showBatchPriorityDialog by remember { mutableStateOf(false) }
    var showDayReport by remember { mutableStateOf(false) }

    BackHandler(enabled = isSelectionMode) {
        viewModel.clearSelection()
    }

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

    completeTaskId?.let { taskId ->
        val task = viewModel.findTask(taskId)
        if (task != null) {
            CompleteTaskDialog(
                task = task,
                onDismiss = { completeTaskId = null },
                onConfirm = { result ->
                    viewModel.completeTask(taskId, result)
                    completeTaskId = null
                },
            )
        } else {
            completeTaskId = null
        }
    }

    resumeTaskId?.let { taskId ->
        val task = viewModel.findTask(taskId)
        if (task != null) {
            ResumeTaskDialog(
                task = task,
                onDismiss = { resumeTaskId = null },
                onConfirm = { comment ->
                    if (viewModel.needsPriorityBeforeStart(taskId)) {
                        priorityStartRequest = PriorityStartRequest(taskId = taskId, resumeComment = comment)
                    } else {
                        viewModel.resumeTask(taskId, comment)
                    }
                    resumeTaskId = null
                },
            )
        } else {
            resumeTaskId = null
        }
    }

    historyTaskId?.let { taskId ->
        val task = viewModel.findTask(taskId)
        if (task != null) {
            SessionHistoryDialog(
                task = task,
                onDismiss = { historyTaskId = null },
            )
        } else {
            historyTaskId = null
        }
    }

    editTaskId?.let { taskId ->
        val task = viewModel.findTask(taskId)
        if (task != null) {
            EditTaskDialog(
                task = task,
                onDismiss = { editTaskId = null },
                onConfirm = { title, description, result ->
                    viewModel.updateTask(taskId, title, description, result)
                    editTaskId = null
                },
            )
        } else {
            editTaskId = null
        }
    }

    priorityStartRequest?.let { request ->
        val task = viewModel.findTask(request.taskId)
        if (task != null) {
            PriorityPickDialog(
                title = stringResource(R.string.priority_start_title),
                taskTitle = task.title,
                initialPriority = taskPriority(task, todayIsoDate()),
                onDismiss = { priorityStartRequest = null },
                onConfirm = { priority ->
                    val resumeComment = request.resumeComment
                    if (resumeComment != null) {
                        viewModel.resumeTaskWithPriority(request.taskId, priority, resumeComment)
                    } else {
                        viewModel.startTaskWithPriority(request.taskId, priority)
                    }
                    priorityStartRequest = null
                },
            )
        } else {
            priorityStartRequest = null
        }
    }

    if (showBatchPriorityDialog && isSelectionMode) {
        PriorityPickDialog(
            title = stringResource(R.string.priority_selected_title),
            taskTitle = stringResource(
                R.string.priority_selected_summary,
                uiState.selectedTaskIds.size,
            ),
            initialPriority = 1,
            onDismiss = { showBatchPriorityDialog = false },
            onConfirm = { priority ->
                viewModel.assignPriorityToSelected(priority)
                showBatchPriorityDialog = false
            },
        )
    } else if (showBatchPriorityDialog) {
        showBatchPriorityDialog = false
    }

    if (showDayReport) {
        DayReportDialog(
            initialDate = todayIsoDate(),
            buildReport = viewModel::dayReport,
            onDismiss = { showDayReport = false },
            onCopy = { text ->
                copyToClipboard(context, text)
                Toast.makeText(context, context.getString(R.string.copied), Toast.LENGTH_SHORT).show()
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
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.priority_filter_label),
                    style = MaterialTheme.typography.bodySmall,
                )
                for (level in 1..4) {
                    FilterChip(
                        selected = level in uiState.priorityFilter,
                        onClick = { viewModel.togglePriorityFilter(level) },
                        label = { Text(level.toString()) },
                    )
                }
                Spacer(modifier = Modifier.weight(1f))
                TextButton(onClick = { showDayReport = true }) {
                    Text(stringResource(R.string.day_report))
                }
            }

            if (isSelectionMode) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = stringResource(
                            R.string.selection_selected_count,
                            uiState.selectedTaskIds.size,
                        ),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Spacer(modifier = Modifier.weight(1f))
                    TextButton(onClick = { showBatchPriorityDialog = true }) {
                        Text(stringResource(R.string.selection_assign_priority))
                    }
                    TextButton(onClick = viewModel::clearSelection) {
                        Text(stringResource(R.string.selection_clear))
                    }
                }
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
                    label = { Text(stringResource(R.string.new_task_label)) },
                    singleLine = true,
                )
                FilledTonalButton(onClick = viewModel::addTask) {
                    Text(stringResource(R.string.add_task))
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
                            priority = taskPriority(task, todayIsoDate()),
                            showSelection = isSelectionMode,
                            selected = task.id in uiState.selectedTaskIds,
                            onLongPress = { viewModel.selectTask(task.id) },
                            onSelectionToggle = { viewModel.toggleTaskSelection(task.id) },
                            onToggle = {
                                if (viewModel.needsPriorityBeforeStart(task.id)) {
                                    priorityStartRequest = PriorityStartRequest(taskId = task.id)
                                } else {
                                    viewModel.toggleTimer(task.id)
                                }
                            },
                            onComplete = { completeTaskId = task.id },
                            onResume = { resumeTaskId = task.id },
                            onHistory = { historyTaskId = task.id },
                            onEdit = { editTaskId = task.id },
                            onDelete = { viewModel.deleteTask(task.id) },
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun TaskRow(
    task: TaskDto,
    durationLabel: String,
    priority: Int,
    showSelection: Boolean,
    selected: Boolean,
    onLongPress: () -> Unit,
    onSelectionToggle: () -> Unit,
    onToggle: () -> Unit,
    onComplete: () -> Unit,
    onResume: () -> Unit,
    onHistory: () -> Unit,
    onEdit: () -> Unit,
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

    val rowModifier = if (showSelection) {
        Modifier
            .fillMaxWidth()
            .combinedClickable(
                onClick = onSelectionToggle,
                onLongClick = onSelectionToggle,
            )
    } else {
        Modifier
            .fillMaxWidth()
            .pointerInput(Unit) {
                detectTapGestures(onLongPress = { onLongPress() })
            }
    }

    Card(modifier = rowModifier) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.Top,
            ) {
                if (showSelection) {
                    Checkbox(
                        checked = selected,
                        onCheckedChange = { onSelectionToggle() },
                    )
                }
                Text(
                    text = priority.toString(),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    modifier = Modifier.weight(1f),
                    text = task.title,
                    style = MaterialTheme.typography.titleMedium.copy(
                        textDecoration = if (isCompleted) TextDecoration.LineThrough else null,
                    ),
                    color = titleColor,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (task.description.isNotBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = task.description,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 4,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (task.result.isNotBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = stringResource(R.string.task_result_label, task.result),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
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
            if (!showSelection) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                ) {
                    IconButton(onClick = onEdit) {
                        Icon(Icons.Default.Edit, contentDescription = stringResource(R.string.task_edit))
                    }
                    IconButton(onClick = onHistory) {
                        Icon(
                            Icons.AutoMirrored.Filled.List,
                            contentDescription = stringResource(R.string.task_history),
                        )
                    }
                    if (!isCompleted) {
                        IconButton(onClick = onToggle) {
                            Icon(
                                imageVector = if (isActive(task)) Icons.Default.Stop else Icons.Default.PlayArrow,
                                contentDescription = if (isActive(task)) "Стоп" else "Старт",
                            )
                        }
                        IconButton(onClick = onComplete) {
                            Icon(Icons.Default.Check, contentDescription = stringResource(R.string.task_complete))
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
                        Icon(Icons.Default.Delete, contentDescription = stringResource(R.string.task_delete))
                    }
                }
            }
        }
    }
}

@Composable
private fun CompleteTaskDialog(
    task: TaskDto,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    var result by rememberSaveable(task.id) { mutableStateOf(task.result) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.complete_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(task.title, style = MaterialTheme.typography.bodyMedium)
                OutlinedTextField(
                    value = result,
                    onValueChange = {
                        result = it
                        error = null
                    },
                    label = { Text(stringResource(R.string.result_field)) },
                    placeholder = { Text(stringResource(R.string.result_placeholder)) },
                    minLines = 3,
                    isError = error != null,
                    supportingText = error?.let { { Text(it) } },
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (result.trim().isEmpty()) {
                        error = "Введите результат выполнения задачи."
                    } else {
                        onConfirm(result)
                    }
                },
            ) {
                Text(stringResource(R.string.task_complete))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.cancel))
            }
        },
    )
}

@Composable
private fun ResumeTaskDialog(
    task: TaskDto,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    var comment by rememberSaveable(task.id) { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.resume_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(task.title, style = MaterialTheme.typography.bodyMedium)
                OutlinedTextField(
                    value = comment,
                    onValueChange = { comment = it },
                    label = { Text(stringResource(R.string.resume_reason_field)) },
                    placeholder = { Text(stringResource(R.string.resume_reason_placeholder)) },
                    minLines = 2,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(comment) }) {
                Text(stringResource(R.string.task_resume))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.cancel))
            }
        },
    )
}

@Composable
private fun EditTaskDialog(
    task: TaskDto,
    onDismiss: () -> Unit,
    onConfirm: (title: String, description: String, result: String) -> Unit,
) {
    var title by rememberSaveable(task.id) { mutableStateOf(task.title) }
    var description by rememberSaveable(task.id) { mutableStateOf(task.description) }
    var result by rememberSaveable(task.id) { mutableStateOf(task.result) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.edit_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = title,
                    onValueChange = {
                        title = it
                        error = null
                    },
                    label = { Text(stringResource(R.string.title_field)) },
                    singleLine = true,
                    isError = error != null,
                )
                OutlinedTextField(
                    value = result,
                    onValueChange = {
                        result = it
                        error = null
                    },
                    label = { Text(stringResource(R.string.result_field)) },
                    minLines = 2,
                    isError = error != null,
                )
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text(stringResource(R.string.description_field)) },
                    minLines = 2,
                )
                error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    when {
                        title.trim().isEmpty() -> error = "Введите название задачи."
                        task.status == TaskStatus.COMPLETED && result.trim().isEmpty() -> {
                            error = "Введите результат выполнения задачи."
                        }
                        else -> onConfirm(title, description, result)
                    }
                },
            ) {
                Text(stringResource(R.string.save))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.cancel))
            }
        },
    )
}

@Composable
private fun PriorityPickDialog(
    title: String,
    taskTitle: String,
    initialPriority: Int,
    onDismiss: () -> Unit,
    onConfirm: (Int) -> Unit,
) {
    var selected by rememberSaveable { mutableStateOf(initialPriority.coerceIn(1, 4)) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(taskTitle, style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (level in 1..4) {
                        FilterChip(
                            selected = selected == level,
                            onClick = { selected = level },
                            label = { Text(level.toString()) },
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(selected) }) {
                Text(stringResource(R.string.save))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.cancel))
            }
        },
    )
}

@Composable
private fun SessionHistoryDialog(
    task: TaskDto,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.history_dialog_title)) },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 420.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(task.title, style = MaterialTheme.typography.bodyMedium)
                if (task.sessions.isEmpty()) {
                    Text(stringResource(R.string.history_empty))
                } else {
                    task.sessions
                        .sortedByDescending { session ->
                            parseInstant(session.startedAt)?.toEpochMilli() ?: Long.MIN_VALUE
                        }
                        .forEach { session ->
                            SessionHistoryRow(session)
                        }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.close))
            }
        },
    )
}

@Composable
private fun SessionHistoryRow(session: SessionDto) {
    val start = formatTaskDateTime(session.startedAt) ?: "—"
    val end = if (session.endedAt == null) {
        stringResource(R.string.session_running)
    } else {
        formatTaskDateTime(session.endedAt) ?: "—"
    }
    val duration = formatDuration(sessionDurationSeconds(session))
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(8.dp)) {
            Text("$start → $end", style = MaterialTheme.typography.bodyMedium)
            Text(
                stringResource(R.string.session_duration, duration),
                style = MaterialTheme.typography.bodySmall,
            )
            if (session.comment.isNotBlank()) {
                Text(
                    stringResource(R.string.session_comment, session.comment),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (!session.bitrixRecordId.isNullOrBlank()) {
                Text(
                    stringResource(R.string.session_transferred, session.bitrixRecordId),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun DayReportDialog(
    initialDate: String,
    buildReport: (String, Boolean) -> String,
    onDismiss: () -> Unit,
    onCopy: (String) -> Unit,
) {
    var dateIso by rememberSaveable { mutableStateOf(initialDate) }
    var extended by rememberSaveable { mutableStateOf(false) }
    var confirmExtended by remember { mutableStateOf(false) }
    val dateValid = parseIsoDateOrNull(dateIso) != null
    val report = remember(dateIso, extended) { buildReport(dateIso, extended) }

    if (confirmExtended) {
        AlertDialog(
            onDismissRequest = { confirmExtended = false },
            title = { Text(stringResource(R.string.day_report_extended_confirm_title)) },
            text = { Text(stringResource(R.string.day_report_extended_confirm_body)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        extended = true
                        confirmExtended = false
                    },
                ) {
                    Text(stringResource(R.string.yes))
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmExtended = false }) {
                    Text(stringResource(R.string.cancel))
                }
            },
        )
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                if (extended) {
                    stringResource(R.string.day_report_extended_title)
                } else {
                    stringResource(R.string.day_report_short_title)
                },
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = dateIso,
                    onValueChange = { dateIso = it },
                    label = { Text(stringResource(R.string.day_report_date)) },
                    singleLine = true,
                    isError = !dateValid,
                    supportingText = if (!dateValid) {
                        { Text(stringResource(R.string.day_report_date_invalid)) }
                    } else {
                        null
                    },
                )
                Text(
                    text = report,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 360.dp)
                        .verticalScroll(rememberScrollState()),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        },
        confirmButton = {
            Row {
                if (!extended) {
                    TextButton(
                        onClick = { confirmExtended = true },
                        enabled = dateValid,
                    ) {
                        Text(stringResource(R.string.day_report_extended))
                    }
                }
                TextButton(
                    onClick = { onCopy(report) },
                    enabled = dateValid,
                ) {
                    Text(stringResource(R.string.copy))
                }
                TextButton(onClick = onDismiss) {
                    Text(stringResource(R.string.close))
                }
            }
        },
    )
}

private fun sessionDurationSeconds(session: SessionDto, nowMillis: Long = System.currentTimeMillis()): Long {
    val start = parseInstant(session.startedAt) ?: return 0L
    val end = session.endedAt?.let(::parseInstant) ?: Instant.ofEpochMilli(nowMillis)
    return (end.epochSecond - start.epochSecond).coerceAtLeast(0)
}

private fun copyToClipboard(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("day-report", text))
}
