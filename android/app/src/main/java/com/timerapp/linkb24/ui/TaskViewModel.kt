package com.timerapp.linkb24.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.timerapp.linkb24.data.AppDataDto
import com.timerapp.linkb24.data.TaskDto
import com.timerapp.linkb24.data.TaskRepository
import com.timerapp.linkb24.data.TaskStatus
import com.timerapp.linkb24.data.formatDuration
import com.timerapp.linkb24.data.isActive
import com.timerapp.linkb24.data.taskDurationSeconds
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class TaskListUiState(
    val tasks: List<TaskDto> = emptyList(),
    val tickMillis: Long = System.currentTimeMillis(),
    val newTaskTitle: String = "",
    val errorMessage: String? = null,
)

class TaskViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = TaskRepository(application)
    private var appData: AppDataDto = repository.load()

    private val _uiState = MutableStateFlow(
        TaskListUiState(tasks = visibleTasks(appData)),
    )
    val uiState: StateFlow<TaskListUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            while (isActive) {
                delay(1_000)
                if (_uiState.value.tasks.any(::isActive)) {
                    _uiState.update { it.copy(tickMillis = System.currentTimeMillis()) }
                }
            }
        }
    }

    fun onNewTaskTitleChange(value: String) {
        _uiState.update { it.copy(newTaskTitle = value, errorMessage = null) }
    }

    fun addTask() {
        val title = _uiState.value.newTaskTitle
        runCatching {
            appData = repository.createTask(title, appData)
            persist()
        }.onSuccess {
            _uiState.update {
                it.copy(newTaskTitle = "", errorMessage = null, tasks = visibleTasks(appData))
            }
        }.onFailure { error ->
            _uiState.update { it.copy(errorMessage = error.message) }
        }
    }

    fun toggleTimer(taskId: String) {
        appData = repository.toggleTimer(taskId, appData)
        persist()
        _uiState.update { it.copy(tasks = visibleTasks(appData), tickMillis = System.currentTimeMillis()) }
    }

    fun completeTask(taskId: String) {
        appData = repository.completeTask(taskId, appData)
        persist()
        _uiState.update { it.copy(tasks = visibleTasks(appData)) }
    }

    fun deleteTask(taskId: String) {
        appData = repository.deleteTask(taskId, appData)
        persist()
        _uiState.update { it.copy(tasks = visibleTasks(appData)) }
    }

    fun durationLabel(task: TaskDto): String {
        return formatDuration(taskDurationSeconds(task, _uiState.value.tickMillis))
    }

    private fun persist() {
        repository.save(appData)
    }

    private fun visibleTasks(data: AppDataDto): List<TaskDto> {
        return data.tasks
            .filter { it.status != TaskStatus.COMPLETED }
            .sortedByDescending { it.createdAt }
    }
}
