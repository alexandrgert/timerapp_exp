package com.timerapp.linkb24.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.timerapp.linkb24.data.ALL_PRIORITIES
import com.timerapp.linkb24.data.AppDataDto
import com.timerapp.linkb24.data.TaskDto
import com.timerapp.linkb24.data.TaskRepository
import com.timerapp.linkb24.data.TaskStatus
import com.timerapp.linkb24.data.TaskViewFilter
import com.timerapp.linkb24.data.WebDavConfigRepository
import com.timerapp.linkb24.data.buildDayReportMarkdown
import com.timerapp.linkb24.data.filterTasks
import com.timerapp.linkb24.data.filterTasksByTitle
import com.timerapp.linkb24.data.formatDuration
import com.timerapp.linkb24.data.isActive
import com.timerapp.linkb24.data.needsPriorityBeforeStart
import com.timerapp.linkb24.data.priorityFilterLevels
import com.timerapp.linkb24.data.taskDurationSeconds
import com.timerapp.linkb24.data.todayIsoDate
import com.timerapp.linkb24.webdav.WebDavDataChangedBus
import com.timerapp.linkb24.webdav.WebDavNotificationHelper
import com.timerapp.linkb24.webdav.WebDavPromptBus
import com.timerapp.linkb24.webdav.WebDavSync
import com.timerapp.linkb24.webdav.clearPendingRemoteRemind
import com.timerapp.linkb24.webdav.withPendingRemoteRemind
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

data class TaskListUiState(
    val tasks: List<TaskDto> = emptyList(),
    val taskFilter: TaskViewFilter = TaskViewFilter.TODAY,
    val priorityFilter: Set<Int> = ALL_PRIORITIES,
    val titleSearchDraft: String = "",
    val titleSearchApplied: String = "",
    val selectedTaskIds: Set<String> = emptySet(),
    val tickMillis: Long = System.currentTimeMillis(),
    val newTaskTitle: String = "",
    val errorMessage: String? = null,
    val syncNotice: String? = null,
    val isWebDavSyncing: Boolean = false,
    val isLoading: Boolean = true,
    val remoteChangePrompt: RemoteChangePrompt? = null,
)

data class RemoteChangePrompt(
    val remoteHash: String,
)

class TaskViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = TaskRepository(application)
    private val webDavSync = WebDavSync(repository, WebDavConfigRepository(application))
    private val configRepository = WebDavConfigRepository(application)
    private var appData: AppDataDto = AppDataDto()

    private val _uiState = MutableStateFlow(TaskListUiState())
    val uiState: StateFlow<TaskListUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            WebDavPromptBus.pending.collect { prompt ->
                if (prompt != null && _uiState.value.remoteChangePrompt == null) {
                    _uiState.update { it.copy(remoteChangePrompt = prompt) }
                }
            }
        }

        viewModelScope.launch {
            WebDavDataChangedBus.events.collect {
                reloadFromDiskAfterExternalSync()
            }
        }

        viewModelScope.launch {
            val notices = mutableListOf<String>()
            runCatching {
                withContext(Dispatchers.IO) {
                    webDavSync.syncOnStartup()
                }
            }.onSuccess { outcome ->
                if (outcome.error.isNotBlank()) {
                    notices += outcome.error
                }
                if (outcome.notice.isNotBlank()) {
                    notices += outcome.notice
                }
            }.onFailure { error ->
                notices += error.message ?: "Ошибка синхронизации WebDAV"
            }

            val pending = withContext(Dispatchers.IO) { configRepository.consumePendingNotice() }
            if (pending.isNotBlank()) {
                notices += pending
            }

            runCatching {
                withContext(Dispatchers.IO) { repository.load() }
            }.onSuccess { loaded ->
                appData = loaded
                publishLoaded(notices.joinToString("\n").ifBlank { null })
            }.onFailure { error ->
                _uiState.update {
                    it.copy(
                        errorMessage = error.message,
                        syncNotice = notices.joinToString("\n").ifBlank { null },
                        isLoading = false,
                    )
                }
            }

            while (isActive) {
                delay(1_000)
                if (appData.tasks.any(::isActive)) {
                    _uiState.update { it.copy(tickMillis = System.currentTimeMillis()) }
                }
            }
        }
    }

    fun onNewTaskTitleChange(value: String) {
        _uiState.update { it.copy(newTaskTitle = value, errorMessage = null) }
    }

    fun onFilterChange(filter: TaskViewFilter) {
        _uiState.update {
            it.copy(
                taskFilter = filter,
                titleSearchDraft = "",
                titleSearchApplied = "",
                tasks = visibleTasks(appData, filter, titleSearch = ""),
            )
        }
    }

    fun onTitleSearchDraftChange(value: String) {
        _uiState.update { it.copy(titleSearchDraft = value) }
    }

    fun applyTitleSearch() {
        val needle = _uiState.value.titleSearchDraft
        _uiState.update {
            it.copy(
                titleSearchApplied = needle,
                tasks = visibleTasks(appData, titleSearch = needle),
            )
        }
    }

    fun selectTask(taskId: String) {
        val task = appData.tasks.firstOrNull { it.id == taskId } ?: return
        _uiState.update {
            it.copy(selectedTaskIds = enterSelection(task.id))
        }
    }

    fun toggleTaskSelection(taskId: String) {
        val task = appData.tasks.firstOrNull { it.id == taskId } ?: return
        _uiState.update {
            it.copy(selectedTaskIds = toggleSelection(it.selectedTaskIds, task.id))
        }
    }

    fun clearSelection() {
        _uiState.update { it.copy(selectedTaskIds = emptySet()) }
    }

    fun togglePriorityFilter(level: Int) {
        mutateTasks("Не удалось обновить фильтр приоритета") { data ->
            val current = priorityFilterLevels(data.ui).toMutableSet()
            if (level in current) {
                if (current.size == 1) {
                    return@mutateTasks data
                }
                current.remove(level)
            } else {
                current.add(level)
            }
            repository.setPriorityFilter(data, current)
        }
    }

    fun addTask() {
        val title = _uiState.value.newTaskTitle
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    val updated = repository.createTask(title, appData)
                    repository.save(updated)
                    updated
                }
            }.onSuccess { updated ->
                appData = updated
                _uiState.update {
                    it.copy(newTaskTitle = "", errorMessage = null, tasks = visibleTasks(appData))
                }
            }.onFailure { error ->
                _uiState.update { it.copy(errorMessage = error.message) }
            }
        }
    }

    fun needsPriorityBeforeStart(taskId: String): Boolean {
        val task = appData.tasks.firstOrNull { it.id == taskId } ?: return false
        return needsPriorityBeforeStart(task, todayIsoDate())
    }

    fun toggleTimer(taskId: String) {
        mutateTasks("Не удалось изменить таймер") { data ->
            repository.toggleTimer(taskId, data)
        }
    }

    fun startTaskWithPriority(taskId: String, priority: Int, keepPriority: Boolean = false) {
        mutateTasks("Не удалось запустить задачу") { data ->
            var updated = repository.setKeepPriority(taskId, data, keepPriority)
            updated = repository.assignTaskPriority(taskId, updated, priority)
            repository.toggleTimer(taskId, updated)
        }
    }

    fun completeTask(taskId: String, result: String) {
        mutateTasks("Не удалось завершить задачу") { data ->
            repository.completeTask(taskId, data, result)
        }
    }

    fun resumeTask(taskId: String, comment: String = "") {
        mutateTasks("Не удалось возобновить задачу") { data ->
            repository.resumeCompletedTask(taskId, data, comment)
        }
    }

    fun resumeTaskWithPriority(
        taskId: String,
        priority: Int,
        comment: String = "",
        keepPriority: Boolean = false,
    ) {
        mutateTasks("Не удалось возобновить задачу") { data ->
            var updated = repository.setKeepPriority(taskId, data, keepPriority)
            updated = repository.assignTaskPriority(taskId, updated, priority)
            repository.resumeCompletedTask(taskId, updated, comment)
        }
    }

    fun assignPriority(taskId: String, priority: Int, keepPriority: Boolean? = null) {
        mutateTasks("Не удалось назначить приоритет") { data ->
            var updated = data
            if (keepPriority != null) {
                updated = repository.setKeepPriority(taskId, updated, keepPriority)
            }
            repository.assignTaskPriority(taskId, updated, priority)
        }
    }

    fun assignPriorityToSelected(priority: Int) {
        val selectedTaskIds = _uiState.value.selectedTaskIds
        if (selectedTaskIds.isEmpty()) {
            return
        }
        mutateTasks(
            errorPrefix = "Не удалось назначить приоритет выбранным задачам",
            clearSelectionIdsOnSuccess = selectedTaskIds,
        ) { data ->
            var updated = data
            for (taskId in selectedTaskIds) {
                updated = repository.assignTaskPriority(taskId, updated, priority)
            }
            updated
        }
    }

    fun updateTask(
        taskId: String,
        title: String,
        description: String,
        result: String,
        keepPriority: Boolean,
    ) {
        mutateTasks("Не удалось сохранить задачу") { data ->
            repository.updateTask(
                taskId,
                data,
                title = title,
                description = description,
                result = result,
                keepPriority = keepPriority,
            )
        }
    }

    fun addHistorySession(taskId: String) {
        mutateTasks("Не удалось добавить запись") { data ->
            val now = OffsetDateTime.now(ZoneId.systemDefault())
            val startedAt = now.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
            val endedAt = now.plusHours(1).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
            repository.addClosedSession(taskId, data, startedAt, endedAt)
        }
    }

    fun deleteTask(taskId: String) {
        mutateTasks("Не удалось удалить задачу") { data ->
            repository.deleteTask(taskId, data)
        }
    }

    fun findTask(taskId: String): TaskDto? = appData.tasks.firstOrNull { it.id == taskId }

    fun durationLabel(task: TaskDto): String {
        return formatDuration(taskDurationSeconds(task, _uiState.value.tickMillis))
    }

    fun dayReport(dateIso: String, extended: Boolean): String {
        return buildDayReportMarkdown(appData, dateIso, extended = extended)
    }

    fun pullWebDav() {
        if (_uiState.value.isWebDavSyncing) {
            return
        }
        val config = configRepository.load()
        if (!config.isConfigured()) {
            _uiState.update { it.copy(syncNotice = "WebDAV не настроен: укажите URL и имя пользователя") }
            return
        }
        viewModelScope.launch {
            val outcome = runWebDavSync { webDavSync.pullAndMerge(config, requireEnabled = false) }
            applySyncOutcome(outcome)
        }
    }

    fun pushWebDav() {
        if (_uiState.value.isWebDavSyncing) {
            return
        }
        val config = configRepository.load()
        if (!config.isConfigured()) {
            _uiState.update { it.copy(syncNotice = "WebDAV не настроен: укажите URL и имя пользователя") }
            return
        }
        viewModelScope.launch {
            val outcome = runWebDavSync { webDavSync.pushLocal(config, requireEnabled = false) }
            applySyncOutcome(outcome)
        }
    }

    fun confirmRemotePull() {
        if (_uiState.value.isWebDavSyncing) {
            return
        }
        WebDavPromptBus.clear()
        WebDavNotificationHelper.cancel(getApplication())
        _uiState.update { it.copy(remoteChangePrompt = null) }
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                val config = configRepository.load().clearPendingRemoteRemind()
                configRepository.save(config)
            }
            val outcome = runWebDavSync { webDavSync.pullAndMerge(requireEnabled = false) }
            applySyncOutcome(outcome)
        }
    }

    fun dismissRemotePull() {
        val remoteHash = _uiState.value.remoteChangePrompt?.remoteHash.orEmpty()
        WebDavPromptBus.clear()
        WebDavNotificationHelper.cancel(getApplication())
        _uiState.update { it.copy(remoteChangePrompt = null) }
        if (remoteHash.isBlank()) {
            return
        }
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                val config = configRepository.load().withPendingRemoteRemind(remoteHash)
                configRepository.save(config)
            }
        }
    }

    fun reloadFromStorage() {
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) { repository.load() }
            }.onSuccess { loaded ->
                appData = loaded
                publishLoaded(null)
            }
        }
    }

    private suspend fun reloadFromDiskAfterExternalSync() {
        if (_uiState.value.isWebDavSyncing) {
            return
        }
        runCatching {
            withContext(Dispatchers.IO) { repository.load() }
        }.onSuccess { loaded ->
            appData = loaded
            publishLoaded(_uiState.value.syncNotice)
        }
    }

    private fun publishLoaded(syncNotice: String?) {
        val selectedTaskIds = pruneSelection(_uiState.value.selectedTaskIds, appData.tasks)
        _uiState.update {
            it.copy(
                tasks = visibleTasks(appData),
                priorityFilter = priorityFilterLevels(appData.ui),
                selectedTaskIds = selectedTaskIds,
                errorMessage = null,
                syncNotice = syncNotice,
                isLoading = false,
            )
        }
    }

    private suspend fun runWebDavSync(
        block: suspend () -> com.timerapp.linkb24.webdav.SyncOutcome,
    ): com.timerapp.linkb24.webdav.SyncOutcome {
        _uiState.update { it.copy(isWebDavSyncing = true, syncNotice = null, errorMessage = null) }
        return runCatching {
            withContext(Dispatchers.IO) { block() }
        }.getOrElse { error ->
            com.timerapp.linkb24.webdav.SyncOutcome(error = error.message ?: "Ошибка WebDAV")
        }
    }

    private suspend fun applySyncOutcome(outcome: com.timerapp.linkb24.webdav.SyncOutcome) {
        if (outcome.data != null) {
            appData = outcome.data
        } else {
            runCatching {
                withContext(Dispatchers.IO) { repository.load() }
            }.onSuccess { loaded ->
                appData = loaded
            }
        }
        _uiState.update {
            val selectedTaskIds = pruneSelection(_uiState.value.selectedTaskIds, appData.tasks)
            it.copy(
                tasks = visibleTasks(appData),
                priorityFilter = priorityFilterLevels(appData.ui),
                selectedTaskIds = selectedTaskIds,
                isWebDavSyncing = false,
                syncNotice = outcome.notice.ifBlank { outcome.error.ifBlank { null } },
                errorMessage = outcome.error.ifBlank { null },
            )
        }
    }

    private fun mutateTasks(
        errorPrefix: String,
        clearSelectionIdsOnSuccess: Set<String> = emptySet(),
        transform: (AppDataDto) -> AppDataDto,
    ) {
        viewModelScope.launch {
            val previous = appData
            runCatching {
                withContext(Dispatchers.IO) {
                    val updated = transform(previous)
                    repository.save(updated)
                    updated
                }
            }.onSuccess { updated ->
                appData = updated
                _uiState.update {
                    val selectedTaskIds = nextSelectionAfterMutation(
                        selectedTaskIds = it.selectedTaskIds,
                        tasks = appData.tasks,
                        clearSelectionIds = clearSelectionIdsOnSuccess,
                    )
                    it.copy(
                        tasks = visibleTasks(appData),
                        priorityFilter = priorityFilterLevels(appData.ui),
                        selectedTaskIds = selectedTaskIds,
                        tickMillis = System.currentTimeMillis(),
                        errorMessage = null,
                    )
                }
            }.onFailure { error ->
                appData = previous
                _uiState.update {
                    it.copy(errorMessage = "$errorPrefix: ${error.message ?: error.javaClass.simpleName}")
                }
            }
        }
    }

    private fun visibleTasks(
        data: AppDataDto,
        filter: TaskViewFilter = _uiState.value.taskFilter,
        titleSearch: String = _uiState.value.titleSearchApplied,
    ): List<TaskDto> {
        return filterTasksByTitle(filterTasks(data, filter), titleSearch)
    }
}
