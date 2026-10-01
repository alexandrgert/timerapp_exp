package com.timerapp.linkb24.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.timerapp.linkb24.data.ALL_PRIORITIES
import com.timerapp.linkb24.data.FocusTimerDto
import com.timerapp.linkb24.data.reconcileFocusTimer
import com.timerapp.linkb24.data.startFocusTimer
import com.timerapp.linkb24.data.stopFocusTimer
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
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class TaskListUiState(
    val tasks: List<TaskDto> = emptyList(),
    val syncConflicts: List<com.timerapp.linkb24.sync.SyncV2.Conflict> = emptyList(),
    val concurrentTasks: List<TaskDto> = emptyList(),
    val focusTimer: FocusTimerDto = FocusTimerDto(),
    val focusTaskTitle: String = "",
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
    private val mutationMutex = Mutex()
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
                if (reconcileFocusTimer(appData) != appData) {
                    mutateTasks("Не удалось завершить концентрацию") { reconcileFocusTimer(it) }
                }
                if (appData.tasks.any(::isActive) || appData.ui.focusTimer.endsAt != null) {
                    _uiState.update { it.copy(tickMillis = System.currentTimeMillis()) }
                }
            }
        }
    }

    fun createTaskFromForm(title: String, description: String, onResult: (String?) -> Unit) {
        mutateTasks("Не удалось создать задачу", onResult = onResult) { data ->
            val created = repository.createTask(title, data)
            repository.updateTask(created.tasks.last().id, created, description = description)
        }
    }

    fun startFocus(taskId: String, minutes: Int, priority: Int?, onResult: (String?) -> Unit) {
        mutateTasks("Не удалось запустить концентрацию", onResult = onResult) { data ->
            var updated = data
            val task = data.tasks.firstOrNull { it.id == taskId }
                ?: throw IllegalArgumentException("Задача не найдена.")
            if (needsPriorityBeforeStart(task, todayIsoDate())) {
                require(priority != null && priority in 1..4) { "Выберите приоритет." }
                updated = repository.assignTaskPriority(taskId, data, priority)
            }
            startFocusTimer(updated, taskId, minutes)
        }
    }

    fun stopFocus() {
        mutateTasks("Не удалось остановить концентрацию") { stopFocusTimer(it) }
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
        createTaskFromForm(_uiState.value.newTaskTitle, "") { error ->
            if (error == null) _uiState.update { it.copy(newTaskTitle = "") }
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
        onResult: (String?) -> Unit,
        original: TaskDto? = null,
    ) {
        mutateTasks("Не удалось сохранить задачу", onResult = onResult) { data ->
            val fresh = data.tasks.firstOrNull { it.id == taskId } ?: error("Задача удалена на другом устройстве")
            val baseline = original ?: fresh
            fun <T> edit(old: T, wanted: T, current: T): T? {
                if (wanted == old) return null
                require(current == old) { "Это поле изменено на другом устройстве. Закройте форму и проверьте новую версию; введённый текст пока сохранён в форме." }
                return wanted
            }
            repository.updateTask(taskId, data,
                title = edit(baseline.title, title, fresh.title),
                description = edit(baseline.description, description, fresh.description),
                result = edit(baseline.result, result, fresh.result),
                keepPriority = edit(baseline.keepPriority, keepPriority, fresh.keepPriority))
        }
    }

    fun saveHistorySession(
        taskId: String, sessionId: String?, startedAt: String, endedAt: String?, comment: String,
        onResult: (String?) -> Unit,
        original: com.timerapp.linkb24.data.SessionDto? = null,
    ) {
        mutateTasks("Не удалось сохранить сессию", onResult = onResult) { data ->
            if (sessionId == null) repository.addClosedSession(taskId, data, startedAt,
                requireNotNull(endedAt) { "Укажите окончание." }, comment)
            else {
                val fresh = data.tasks.firstOrNull { it.id == taskId }?.sessions?.firstOrNull { it.id == sessionId }
                    ?: error("Сессия удалена на другом устройстве")
                val baseline = original ?: fresh
                repository.updateSessionFromSnapshot(taskId, data, baseline, startedAt, endedAt, comment)
            }
        }
    }

    fun deleteHistorySession(taskId: String, sessionId: String, onResult: (String?) -> Unit, original: com.timerapp.linkb24.data.SessionDto? = null) {
        mutateTasks("Не удалось удалить сессию", onResult = onResult) { data ->
            require(original == null || data.tasks.firstOrNull { it.id == taskId }?.sessions?.firstOrNull { it.id == sessionId } == original) { "Сессия изменилась. Проверьте её перед удалением." }
            repository.deleteSession(taskId, sessionId, data)
        }
    }

    fun deleteTask(taskId: String, onResult: (String?) -> Unit, original: TaskDto? = null) {
        mutateTasks("Не удалось удалить задачу", onResult = onResult) { data ->
            require(original == null || data.tasks.firstOrNull { it.id == taskId } == original) { "Задача изменилась. Проверьте её перед удалением." }
            repository.deleteTask(taskId, data)
        }
    }

    fun resolveSyncConflict(conflict: com.timerapp.linkb24.sync.SyncV2.Conflict, value: kotlinx.serialization.json.JsonElement) {
        viewModelScope.launch {
            runCatching { withContext(Dispatchers.IO) { repository.resolveSync(conflict, value) } }
                .onSuccess { appData = it; publishLoaded("Вариант сохранён. Синхронизируйте устройства.") }
                .onFailure { error -> _uiState.update { it.copy(errorMessage = error.message) } }
        }
    }

    fun resolveConcurrentTimer(taskId: String, sessionId: String, expected: Set<Pair<String, String>>) {
        mutateTasks("Не удалось разрешить одновременные таймеры") { data ->
            val current = data.tasks.flatMap { task -> task.sessions.filter { it.endedAt == null }.map { task.id to it.id } }.toSet()
            require(current == expected) { "Список работающих сессий изменился. Проверьте его и выберите снова." }
            require(data.tasks.any { t -> t.id == taskId && t.sessions.any { s -> s.id == sessionId && s.endedAt == null } }) { "Выбранная сессия уже завершена. Обновите список." }
            val now = java.time.Instant.now()
            data.copy(tasks = data.tasks.map { task ->
                val sessions = task.sessions.map { session ->
                    if (session.endedAt != null || (task.id == taskId && session.id == sessionId)) session
                    else session.copy(endedAt = maxOf(com.timerapp.linkb24.data.parseInstant(session.startedAt) ?: now, now).toString())
                }
                task.copy(sessions = sessions, status = if (task.status == TaskStatus.COMPLETED) task.status else if (sessions.any { it.endedAt == null }) TaskStatus.RUNNING else if (sessions.isEmpty()) task.status else TaskStatus.PAUSED)
            })
        }
    }

    fun hasConfiguredSync(): Boolean = configRepository.load().let { it.enabled || it.isConfigured() }

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
                syncConflicts = appData.syncConflicts,
                concurrentTasks = if (appData.tasks.sumOf { t -> t.sessions.count { s -> s.endedAt == null } } > 1) appData.tasks else emptyList(),
                focusTimer = appData.ui.focusTimer,
                focusTaskTitle = appData.tasks.firstOrNull { task -> task.id == appData.ui.focusTimer.sessionTaskId }?.title.orEmpty(),
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
            appData = reconcileFocusTimer(outcome.data)
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
                syncConflicts = appData.syncConflicts,
                concurrentTasks = if (appData.tasks.sumOf { t -> t.sessions.count { s -> s.endedAt == null } } > 1) appData.tasks else emptyList(),
                focusTimer = appData.ui.focusTimer,
                focusTaskTitle = appData.tasks.firstOrNull { task -> task.id == appData.ui.focusTimer.sessionTaskId }?.title.orEmpty(),
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
        onResult: (String?) -> Unit = {},
        transform: (AppDataDto) -> AppDataDto,
    ) {
        viewModelScope.launch {
            mutationMutex.withLock {
                val previous = appData
                runCatching {
                    withContext(Dispatchers.IO) {
                        repository.mutate { fresh -> transform(fresh) }
                    }
                }.onSuccess { updated ->
                    runCatching {
                        com.timerapp.linkb24.focus.FocusAlarmScheduler.update(getApplication(), previous)
                        com.timerapp.linkb24.focus.FocusAlarmScheduler.update(getApplication(), updated)
                    }
                    appData = updated
                    _uiState.update {
                        val selectedTaskIds = nextSelectionAfterMutation(
                            selectedTaskIds = it.selectedTaskIds,
                            tasks = appData.tasks,
                            clearSelectionIds = clearSelectionIdsOnSuccess,
                        )
                        it.copy(
                            tasks = visibleTasks(appData),
                syncConflicts = appData.syncConflicts,
                concurrentTasks = if (appData.tasks.sumOf { t -> t.sessions.count { s -> s.endedAt == null } } > 1) appData.tasks else emptyList(),
                            focusTimer = appData.ui.focusTimer,
                            focusTaskTitle = appData.tasks.firstOrNull { task -> task.id == appData.ui.focusTimer.sessionTaskId }?.title.orEmpty(),
                            priorityFilter = priorityFilterLevels(appData.ui),
                            selectedTaskIds = selectedTaskIds,
                            tickMillis = System.currentTimeMillis(),
                            errorMessage = com.timerapp.linkb24.focus.FocusAlarmScheduler.lastError,
                        )
                    }
                    onResult(null)
                }.onFailure { error ->
                    appData = previous
                    _uiState.update {
                        it.copy(errorMessage = "$errorPrefix: ${error.message ?: error.javaClass.simpleName}")
                    }
                    onResult("$errorPrefix: ${error.message ?: "Ошибка сохранения"}")
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
