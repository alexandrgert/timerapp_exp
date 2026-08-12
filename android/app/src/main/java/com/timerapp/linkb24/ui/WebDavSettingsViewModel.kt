package com.timerapp.linkb24.ui

import android.app.Application
import android.content.Intent
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.timerapp.linkb24.data.AppPrefs
import com.timerapp.linkb24.data.AppPrefsRepository
import com.timerapp.linkb24.data.DEFAULT_UPDATE_CHECK_INTERVAL_DAYS
import com.timerapp.linkb24.data.DEFAULT_UPDATE_GITHUB_REPO
import com.timerapp.linkb24.data.MAX_UPDATE_CHECK_INTERVAL_DAYS
import com.timerapp.linkb24.data.MIN_UPDATE_CHECK_INTERVAL_DAYS
import com.timerapp.linkb24.data.SettingsBundle
import com.timerapp.linkb24.data.TaskRepository
import com.timerapp.linkb24.data.WebDavConfig
import com.timerapp.linkb24.data.WebDavConfigRepository
import com.timerapp.linkb24.data.normalizeGithubRepo
import com.timerapp.linkb24.data.normalizeSyncIntervalMinutes
import com.timerapp.linkb24.data.validateWebDavConfig
import com.timerapp.linkb24.update.UpdateChecker
import com.timerapp.linkb24.webdav.WebDavClient
import com.timerapp.linkb24.webdav.WebDavException
import com.timerapp.linkb24.webdav.WebDavSync
import com.timerapp.linkb24.webdav.WebDavSyncLog
import com.timerapp.linkb24.webdav.normalizeRemindLaterMinutes
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class WebDavSettingsUiState(
    val enabled: Boolean = false,
    val url: String = "",
    val username: String = "",
    val password: String = "",
    val remotePath: String = "",
    val syncOnStartup: Boolean = true,
    val syncOnShutdown: Boolean = true,
    val shutdownUploadOnly: Boolean = false,
    val syncIntervalMinutes: String = "0",
    val syncRemindLaterMinutes: Int = 15,
    val showPassword: Boolean = false,
    val lastSyncAt: String? = null,
    val lastError: String = "",
    val statusMessage: String? = null,
    val isTesting: Boolean = false,
    val isSaving: Boolean = false,
    val isSyncing: Boolean = false,
    val isCheckingUpdates: Boolean = false,
    val errorMessage: String? = null,
    val savedMessage: String? = null,
    val checkUpdates: Boolean = false,
    val updateCheckIntervalDays: String = DEFAULT_UPDATE_CHECK_INTERVAL_DAYS.toString(),
    val updateGithubRepo: String = DEFAULT_UPDATE_GITHUB_REPO,
    val updateStatusMessage: String? = null,
    val updateReleaseUrl: String? = null,
    val showLogDialog: Boolean = false,
    val logText: String = "",
    val settingsIoMessage: String? = null,
    val pendingImportConfirmStep: Int = 0,
    val pendingImportUri: String? = null,
)

class WebDavSettingsViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = WebDavConfigRepository(application)
    private val appPrefsRepository = AppPrefsRepository(application)
    private val syncLog = WebDavSyncLog(application)
    private val webDavSync = WebDavSync(TaskRepository(application), repository, syncLog)

    private val _uiState = MutableStateFlow(WebDavSettingsUiState())
    val uiState: StateFlow<WebDavSettingsUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        val config = repository.load()
        val prefs = appPrefsRepository.load()
        _uiState.value = config.toUiState(prefs)
    }

    fun onEnabledChange(value: Boolean) {
        _uiState.update { it.copy(enabled = value, errorMessage = null, savedMessage = null) }
    }

    fun onUrlChange(value: String) {
        _uiState.update { it.copy(url = value, errorMessage = null, savedMessage = null) }
    }

    fun onUsernameChange(value: String) {
        _uiState.update { it.copy(username = value, errorMessage = null, savedMessage = null) }
    }

    fun onPasswordChange(value: String) {
        _uiState.update { it.copy(password = value, errorMessage = null, savedMessage = null) }
    }

    fun onRemotePathChange(value: String) {
        _uiState.update { it.copy(remotePath = value, errorMessage = null, savedMessage = null) }
    }

    fun onSyncOnStartupChange(value: Boolean) {
        _uiState.update { it.copy(syncOnStartup = value, savedMessage = null) }
    }

    fun onSyncOnShutdownChange(value: Boolean) {
        _uiState.update { it.copy(syncOnShutdown = value, savedMessage = null) }
    }

    fun onShutdownUploadOnlyChange(value: Boolean) {
        _uiState.update { it.copy(shutdownUploadOnly = value, savedMessage = null) }
    }

    fun onSyncIntervalMinutesChange(value: String) {
        _uiState.update { it.copy(syncIntervalMinutes = value.filter { it.isDigit() }, savedMessage = null) }
    }

    fun onSyncRemindLaterMinutesChange(value: Int) {
        _uiState.update { it.copy(syncRemindLaterMinutes = value, savedMessage = null) }
    }

    fun onCheckUpdatesChange(value: Boolean) {
        _uiState.update { it.copy(checkUpdates = value, savedMessage = null) }
    }

    fun onUpdateCheckIntervalDaysChange(value: String) {
        _uiState.update {
            it.copy(
                updateCheckIntervalDays = value.filter { ch -> ch.isDigit() },
                savedMessage = null,
            )
        }
    }

    fun onUpdateGithubRepoChange(value: String) {
        _uiState.update { it.copy(updateGithubRepo = value, savedMessage = null) }
    }

    fun toggleShowPassword() {
        _uiState.update { it.copy(showPassword = !it.showPassword) }
    }

    fun exportSettingsJson(): String {
        val webdav = _uiState.value.toConfig()
        val app = _uiState.value.toAppPrefs()
        return SettingsBundle.exportJson(webdav, app)
    }

    fun beginImportFromUri(uri: Uri) {
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    val context = getApplication<Application>()
                    val raw = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                        ?: error("Не удалось прочитать файл")
                    val parsed = SettingsBundle.parse(raw)
                    if (!parsed.ok) {
                        error(parsed.error)
                    }
                }
            }.onSuccess {
                _uiState.update {
                    it.copy(
                        pendingImportUri = uri.toString(),
                        pendingImportConfirmStep = 1,
                        settingsIoMessage = null,
                    )
                }
            }.onFailure { error ->
                _uiState.update {
                    it.copy(
                        pendingImportConfirmStep = 0,
                        pendingImportUri = null,
                        settingsIoMessage = error.message ?: "Не удалось прочитать файл настроек",
                    )
                }
            }
        }
    }

    fun cancelImportConfirm() {
        _uiState.update {
            it.copy(pendingImportConfirmStep = 0, pendingImportUri = null)
        }
    }

    fun advanceImportConfirm() {
        val step = _uiState.value.pendingImportConfirmStep
        when (step) {
            1 -> _uiState.update { it.copy(pendingImportConfirmStep = 2) }
            2 -> {
                val uriText = _uiState.value.pendingImportUri
                _uiState.update { it.copy(pendingImportConfirmStep = 0, pendingImportUri = null) }
                if (!uriText.isNullOrBlank()) {
                    applyImportFromUri(Uri.parse(uriText))
                }
            }
            else -> cancelImportConfirm()
        }
    }

    private fun applyImportFromUri(uri: Uri) {
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    val context = getApplication<Application>()
                    val raw = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                        ?: error("Не удалось прочитать файл")
                    val parsed = SettingsBundle.parse(raw)
                    if (!parsed.ok) {
                        error(parsed.error)
                    }
                    val currentWebdav = repository.load()
                    if (parsed.webdav != null) {
                        repository.save(SettingsBundle.mergeImportedWebDav(parsed.webdav, currentWebdav))
                    }
                    if (parsed.app != null) {
                        appPrefsRepository.save(parsed.app)
                    }
                }
            }.onSuccess {
                load()
                (getApplication() as com.timerapp.linkb24.TimerApplication).restartWebDavPeriodicMonitor()
                _uiState.update {
                    it.copy(settingsIoMessage = "Настройки импортированы и сохранены")
                }
            }.onFailure { error ->
                _uiState.update {
                    it.copy(settingsIoMessage = error.message ?: "Не удалось импортировать настройки")
                }
            }
        }
    }

    fun markExportOk(name: String) {
        _uiState.update { it.copy(settingsIoMessage = "Настройки экспортированы: $name") }
    }

    fun markExportFailed(message: String) {
        _uiState.update { it.copy(settingsIoMessage = message) }
    }

    fun openLog() {
        _uiState.update {
            it.copy(showLogDialog = true, logText = syncLog.formatForDisplay())
        }
    }

    fun refreshLog() {
        _uiState.update { it.copy(logText = syncLog.formatForDisplay()) }
    }

    fun clearLog() {
        syncLog.clear()
        _uiState.update { it.copy(logText = syncLog.formatForDisplay()) }
    }

    fun dismissLog() {
        _uiState.update { it.copy(showLogDialog = false) }
    }

    fun save(): Boolean {
        val config = _uiState.value.toConfig()
        val validationError = validateWebDavConfig(config)
        if (validationError != null) {
            _uiState.update { it.copy(errorMessage = validationError, savedMessage = null) }
            return false
        }
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, errorMessage = null, savedMessage = null) }
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.save(config.withDeviceId())
                    appPrefsRepository.save(_uiState.value.toAppPrefs())
                }
            }.onSuccess {
                (getApplication() as com.timerapp.linkb24.TimerApplication).restartWebDavPeriodicMonitor()
                _uiState.update {
                    it.copy(
                        isSaving = false,
                        savedMessage = "Настройки сохранены",
                        statusMessage = statusText(config),
                    )
                }
            }.onFailure { error ->
                _uiState.update {
                    it.copy(
                        isSaving = false,
                        errorMessage = error.message ?: "Не удалось сохранить настройки",
                    )
                }
            }
        }
        return true
    }

    fun testConnection() {
        val config = _uiState.value.toConfig()
        val validationError = validateWebDavConfig(config.takeIf { it.enabled } ?: config.copy(enabled = true))
        if (validationError != null) {
            _uiState.update { it.copy(errorMessage = validationError) }
            return
        }
        viewModelScope.launch {
            _uiState.update {
                it.copy(isTesting = true, errorMessage = null, statusMessage = null, savedMessage = null)
            }
            runCatching {
                withContext(Dispatchers.IO) {
                    WebDavClient(config.copy(enabled = true)).testConnection()
                }
            }.onSuccess { message ->
                _uiState.update {
                    it.copy(isTesting = false, statusMessage = message, lastError = "")
                }
            }.onFailure { error ->
                val text = when (error) {
                    is WebDavException -> error.message ?: "Ошибка WebDAV"
                    else -> error.message ?: "Ошибка WebDAV"
                }
                _uiState.update {
                    it.copy(isTesting = false, errorMessage = text, lastError = text)
                }
            }
        }
    }

    fun checkUpdatesNow() {
        viewModelScope.launch {
            _uiState.update {
                it.copy(isCheckingUpdates = true, updateStatusMessage = null, updateReleaseUrl = null)
            }
            val result = withContext(Dispatchers.IO) {
                val prefs = appPrefsRepository.load()
                val repo = normalizeGithubRepo(_uiState.value.updateGithubRepo)
                UpdateChecker.checkForUpdate(
                    dismissedVersion = prefs.dismissedUpdateVersion,
                    respectDismissed = false,
                    githubRepo = repo,
                )
            }
            appPrefsRepository.markCheckDone(
                dismissedVersion = if (result.updateAvailable) result.latest?.version else null,
            )
            _uiState.update {
                when {
                    !result.ok -> it.copy(
                        isCheckingUpdates = false,
                        updateStatusMessage = result.error.ifBlank { "Не удалось проверить обновления" },
                    )
                    result.updateAvailable && result.latest != null -> it.copy(
                        isCheckingUpdates = false,
                        updateStatusMessage = "Доступна версия ${result.latest.version}",
                        updateReleaseUrl = result.latest.htmlUrl,
                    )
                    else -> it.copy(
                        isCheckingUpdates = false,
                        updateStatusMessage = "Установлена актуальная версия",
                        updateReleaseUrl = null,
                    )
                }
            }
        }
    }

    fun openUpdateRelease() {
        val url = _uiState.value.updateReleaseUrl ?: return
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        getApplication<Application>().startActivity(intent)
    }

    fun pullNow(onComplete: () -> Unit = {}) {
        if (!persistFormConfig()) {
            return
        }
        syncAction(onComplete = onComplete) { config ->
            webDavSync.pullAndMerge(config, requireEnabled = false)
        }
    }

    fun pushNow(onComplete: () -> Unit = {}) {
        if (!persistFormConfig()) {
            return
        }
        syncAction(onComplete = onComplete) { config ->
            webDavSync.pushLocal(config, requireEnabled = false)
        }
    }

    private fun persistFormConfig(): Boolean {
        val config = _uiState.value.toConfig()
        val validationError = validateWebDavConfig(config.copy(enabled = true))
        if (validationError != null) {
            _uiState.update { it.copy(errorMessage = validationError) }
            return false
        }
        repository.save(config.withDeviceId())
        appPrefsRepository.save(_uiState.value.toAppPrefs())
        return true
    }

    private fun syncAction(
        onComplete: () -> Unit,
        block: suspend (WebDavConfig) -> com.timerapp.linkb24.webdav.SyncOutcome,
    ) {
        val config = repository.load()
        viewModelScope.launch {
            _uiState.update {
                it.copy(isSyncing = true, errorMessage = null, savedMessage = null)
            }
            runCatching {
                withContext(Dispatchers.IO) { block(config) }
            }.onSuccess { outcome ->
                load()
                _uiState.update {
                    it.copy(
                        isSyncing = false,
                        statusMessage = outcome.notice.ifBlank {
                            outcome.error.ifBlank { "Синхронизация завершена" }
                        },
                        errorMessage = outcome.error.ifBlank { null },
                    )
                }
                onComplete()
            }.onFailure { error ->
                val text = when (error) {
                    is WebDavException -> error.message ?: "Ошибка WebDAV"
                    else -> error.message ?: "Ошибка WebDAV"
                }
                _uiState.update {
                    it.copy(isSyncing = false, errorMessage = text, lastError = text)
                }
            }
        }
    }

    private fun WebDavConfig.toUiState(prefs: AppPrefs): WebDavSettingsUiState {
        return WebDavSettingsUiState(
            enabled = enabled,
            url = url,
            username = username,
            password = password,
            remotePath = remotePath,
            syncOnStartup = syncOnStartup,
            syncOnShutdown = syncOnShutdown,
            shutdownUploadOnly = shutdownUploadOnly,
            syncIntervalMinutes = syncIntervalMinutes.toString(),
            syncRemindLaterMinutes = normalizeRemindLaterMinutes(syncRemindLaterMinutes),
            lastSyncAt = lastSyncAt,
            lastError = lastError,
            statusMessage = statusText(this),
            checkUpdates = prefs.checkUpdates,
            updateCheckIntervalDays = prefs.updateCheckIntervalDays.toString(),
            updateGithubRepo = prefs.updateGithubRepo,
        )
    }

    private fun WebDavSettingsUiState.toConfig(): WebDavConfig {
        val current = repository.load()
        return WebDavConfig(
            enabled = enabled,
            url = url.trim(),
            username = username.trim(),
            password = password,
            remotePath = remotePath.trim().ifEmpty { com.timerapp.linkb24.data.DEFAULT_WEBDAV_REMOTE_PATH },
            syncOnStartup = syncOnStartup,
            syncOnShutdown = syncOnShutdown,
            shutdownUploadOnly = shutdownUploadOnly,
            syncIntervalMinutes = normalizeSyncIntervalMinutes(syncIntervalMinutes.toIntOrNull() ?: 0),
            syncRemindLaterMinutes = normalizeRemindLaterMinutes(syncRemindLaterMinutes),
            lastSyncAt = current.lastSyncAt,
            lastError = current.lastError,
            deviceId = current.deviceId,
            lastRemoteContentHash = current.lastRemoteContentHash,
            lastSyncHadConflict = current.lastSyncHadConflict,
            pendingNotice = current.pendingNotice,
            pendingRemoteHash = current.pendingRemoteHash,
            pendingRemoteRemindAt = current.pendingRemoteRemindAt,
        ).withDeviceId()
    }

    private fun WebDavSettingsUiState.toAppPrefs(): AppPrefs {
        val current = appPrefsRepository.load()
        val days = updateCheckIntervalDays.toIntOrNull()
            ?.coerceIn(MIN_UPDATE_CHECK_INTERVAL_DAYS, MAX_UPDATE_CHECK_INTERVAL_DAYS)
            ?: DEFAULT_UPDATE_CHECK_INTERVAL_DAYS
        return current.copy(
            checkUpdates = checkUpdates,
            updateCheckIntervalDays = days,
            updateGithubRepo = normalizeGithubRepo(updateGithubRepo),
        )
    }

    private fun statusText(config: WebDavConfig): String {
        val parts = mutableListOf<String>()
        if (config.lastSyncAt != null) {
            parts += "Последняя синхронизация: ${config.lastSyncAt}"
        }
        if (config.lastError.isNotBlank()) {
            parts += "Ошибка: ${config.lastError}"
        }
        if (parts.isEmpty()) {
            return if (config.enabled) "Синхронизация включена" else "Синхронизация выключена"
        }
        return parts.joinToString("\n")
    }
}
