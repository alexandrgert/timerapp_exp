package com.timerapp.linkb24.webdav

import com.timerapp.linkb24.data.AppDataDto
import com.timerapp.linkb24.data.TaskRepository
import com.timerapp.linkb24.data.WebDavConfig
import com.timerapp.linkb24.data.WebDavConfigRepository
import com.timerapp.linkb24.data.mergeDataFiles

data class SyncOutcome(
    val data: AppDataDto? = null,
    val error: String = "",
    val conflictDetected: Boolean = false,
    val notice: String = "",
    val uploadedTasks: Int = 0,
    val downloadedTasks: Int = 0,
)

data class RemoteCheckOutcome(
    val remoteChanged: Boolean = false,
    val remoteHash: String = "",
    val error: String = "",
)

class WebDavSync(
    private val taskRepository: TaskRepository,
    private val configRepository: WebDavConfigRepository,
    private val syncLog: WebDavSyncLog = WebDavSyncLog(
        java.io.File(taskRepository.dataFile.parentFile, WebDavSyncLog.LOG_FILENAME),
    ),
) {
    private fun logOutcome(
        op: String,
        outcome: SyncOutcome,
        uploadedTasks: Int = outcome.uploadedTasks,
        downloadedTasks: Int = outcome.downloadedTasks,
    ): SyncOutcome {
        syncLog.append(
            op = op,
            uploadedTasks = uploadedTasks,
            downloadedTasks = downloadedTasks,
            ok = outcome.error.isBlank(),
            error = outcome.error,
        )
        return outcome.copy(uploadedTasks = uploadedTasks, downloadedTasks = downloadedTasks)
    }

    fun syncOnStartup(): SyncOutcome {
        val config = configRepository.load()
        if (!config.enabled || !config.syncOnStartup) {
            return SyncOutcome()
        }
        return runCatching {
            pullAndMerge(config, requireEnabled = true, logOp = "startup")
        }.getOrElse { error ->
            val message = syncErrorMessage(error)
            configRepository.markSyncError(config, message)
            SyncOutcome(error = message)
        }
    }

    fun syncOnShutdown(): SyncOutcome {
        val config = configRepository.load()
        if (!config.enabled || !config.syncOnShutdown) {
            return SyncOutcome()
        }
        return runCatching {
            val outcome = if (config.shutdownUploadOnly) {
                pushLocalUploadOnly(config, requireEnabled = true, logOp = "shutdown")
            } else {
                pushLocal(config, requireEnabled = true, logOp = "shutdown")
            }
            if (outcome.notice.isNotBlank() && outcome.conflictDetected) {
                configRepository.savePendingNotice(outcome.notice)
            }
            outcome
        }.getOrElse { error ->
            val message = syncErrorMessage(error)
            configRepository.markSyncError(config, message)
            SyncOutcome(error = message)
        }
    }

    fun syncOnReconnect(): SyncOutcome {
        val config = configRepository.load()
        if (!config.enabled || !config.isConfigured()) {
            return SyncOutcome()
        }
        return runCatching {
            pushLocal(config, requireEnabled = true, logOp = "reconnect_push")
        }.getOrElse { error ->
            val message = syncErrorMessage(error)
            configRepository.markSyncError(config, message)
            SyncOutcome(error = message)
        }
    }

    fun checkRemoteOnPeriodic(): RemoteCheckOutcome {
        val config = configRepository.load()
        if (!config.periodicSyncEnabled()) {
            return RemoteCheckOutcome()
        }
        return checkRemoteChanges(config, requireEnabled = true)
    }

    fun checkRemoteChanges(
        config: WebDavConfig = configRepository.load(),
        requireEnabled: Boolean = true,
    ): RemoteCheckOutcome {
        if (requireEnabled && !config.enabled) {
            return RemoteCheckOutcome()
        }
        if (!config.isConfigured()) {
            return RemoteCheckOutcome(error = "WebDAV не настроен: укажите URL и имя пользователя")
        }
        return runCatching {
            val client = WebDavClient(config.withDeviceId())
            if (!client.exists()) {
                return RemoteCheckOutcome()
            }
            val remotePayload = client.download()
            val remoteMeta = readRemoteMeta(client, config)
            val remoteHash = remotePayloadHash(remotePayload, remoteMeta)
            val dataFile = taskRepository.dataFile
            val localHash = if (dataFile.isFile) contentHash(dataFile.readBytes()) else ""
            val changed = remoteChangedSinceSync(config, remoteHash, localHash)
            RemoteCheckOutcome(remoteChanged = changed, remoteHash = remoteHash)
        }.getOrElse { error ->
            RemoteCheckOutcome(error = syncErrorMessage(error))
        }
    }

    fun syncNow(
        config: WebDavConfig = configRepository.load(),
        requireEnabled: Boolean = false,
    ): SyncOutcome {
        if (requireEnabled && !config.enabled) {
            return SyncOutcome(error = "Синхронизация WebDAV отключена")
        }
        if (!config.isConfigured()) {
            return SyncOutcome(error = "WebDAV не настроен: укажите URL и имя пользователя")
        }
        return runCatching {
            val pullOutcome = pullAndMerge(config, requireEnabled = false, logOp = "sync_pull")
            val pushOutcome = pushMerged(config, requireEnabled = false, logOp = "sync_push")
            val notices = listOf(pullOutcome.notice, pushOutcome.notice).filter { it.isNotBlank() }
            SyncOutcome(
                data = pushOutcome.data ?: pullOutcome.data,
                conflictDetected = pullOutcome.conflictDetected || pushOutcome.conflictDetected,
                notice = notices.joinToString(" ").ifBlank { "Синхронизация завершена" },
                uploadedTasks = pushOutcome.uploadedTasks,
                downloadedTasks = pullOutcome.downloadedTasks,
            )
        }.getOrElse { error ->
            val message = syncErrorMessage(error)
            configRepository.markSyncError(config, message)
            SyncOutcome(error = message)
        }
    }

    fun pullAndMerge(
        config: WebDavConfig = configRepository.load(),
        requireEnabled: Boolean = true,
        logOp: String = "pull",
    ): SyncOutcome {
        if (requireEnabled && !config.enabled) {
            throw WebDavException("Синхронизация WebDAV отключена")
        }
        return try {
            val client = WebDavClient(config.withDeviceId())
            var conflictDetected = false
            val dataFile = taskRepository.dataFile
            val remoteFound = client.exists()
            var downloadedTasks = 0

            val merged = if (remoteFound) {
                val remotePayload = client.download()
                downloadedTasks = WebDavSyncLog.countTasksInPayload(remotePayload)
                val remoteMeta = readRemoteMeta(client, config)
                val remoteHash = remotePayloadHash(remotePayload, remoteMeta)
                val localHash = if (dataFile.isFile) contentHash(dataFile.readBytes()) else ""
                if (remoteChangedSinceSync(config, remoteHash, localHash)) {
                    conflictDetected = true
                }
                mergeDataFiles(dataFile, remotePayload)
            } else if (dataFile.isFile) {
                taskRepository.load()
            } else {
                AppDataDto()
            }

            val finalized = finalizeMergedState(merged)
            val remoteHash = contentHash(dataFile.readBytes())
            configRepository.markSyncOk(config.withDeviceId(), remoteHash, conflictDetected)

            val notice = when {
                conflictDetected -> "Обнаружен конфликт версий: данные объединены с сервера."
                !remoteFound && merged.tasks.isEmpty() ->
                    "Файл ${config.remotePath} на сервере не найден. " +
                        "Сначала загрузите data.json с компьютера или нажмите «Загрузить сейчас»."
                !remoteFound ->
                    "Файл ${config.remotePath} на сервере не найден — использована локальная копия."
                else -> ""
            }
            logOutcome(
                logOp,
                SyncOutcome(
                    data = finalized,
                    conflictDetected = conflictDetected,
                    notice = notice,
                    downloadedTasks = downloadedTasks,
                ),
            )
        } catch (error: WebDavException) {
            logOutcome(logOp, SyncOutcome(error = syncErrorMessage(error)))
            throw error
        }
    }

    fun pushLocal(
        config: WebDavConfig = configRepository.load(),
        requireEnabled: Boolean = true,
        logOp: String = "push",
    ): SyncOutcome {
        if (requireEnabled && !config.enabled) {
            throw WebDavException("Синхронизация WebDAV отключена")
        }
        val dataFile = taskRepository.dataFile
        if (!dataFile.isFile) {
            throw WebDavException("Локальный файл данных не найден")
        }

        return try {
            val client = WebDavClient(config.withDeviceId())
            var conflictDetected = false
            var merged = taskRepository.load()
            var downloadedTasks = 0

            if (client.exists()) {
                val remotePayload = client.download()
                downloadedTasks = WebDavSyncLog.countTasksInPayload(remotePayload)
                val remoteMeta = readRemoteMeta(client, config)
                val remoteHash = remotePayloadHash(remotePayload, remoteMeta)
                val localHash = contentHash(dataFile.readBytes())
                if (remoteChangedSinceSync(config, remoteHash, localHash)) {
                    conflictDetected = true
                }
                merged = mergeDataFiles(dataFile, remotePayload)
                merged = finalizeMergedState(merged)
            } else {
                merged = finalizeMergedState(merged)
            }

            val payload = dataFile.readBytes()
            val uploadedTasks = WebDavSyncLog.countTasksInPayload(payload)
            val meta = uploadPayload(client, config.withDeviceId(), payload)
            configRepository.markSyncOk(config.withDeviceId(), meta.contentHash, conflictDetected)

            val notice = if (conflictDetected) {
                "Перед загрузкой выполнено слияние с более новой версией на сервере."
            } else {
                ""
            }
            logOutcome(
                logOp,
                SyncOutcome(
                    data = merged,
                    conflictDetected = conflictDetected,
                    notice = notice,
                    uploadedTasks = uploadedTasks,
                    downloadedTasks = downloadedTasks,
                ),
            )
        } catch (error: WebDavException) {
            logOutcome(logOp, SyncOutcome(error = syncErrorMessage(error)))
            throw error
        }
    }

    fun pushMerged(
        config: WebDavConfig = configRepository.load(),
        requireEnabled: Boolean = true,
        logOp: String? = null,
    ): SyncOutcome {
        if (requireEnabled && !config.enabled) {
            throw WebDavException("Синхронизация WebDAV отключена")
        }
        val dataFile = taskRepository.dataFile
        if (!dataFile.isFile) {
            throw WebDavException("Локальный файл данных не найден")
        }

        return try {
            val merged = TaskRepository.prepareLoadedData(taskRepository.load())
            taskRepository.save(merged)
            val client = WebDavClient(config.withDeviceId())
            val payload = dataFile.readBytes()
            val uploadedTasks = WebDavSyncLog.countTasksInPayload(payload)
            val meta = uploadPayload(client, config.withDeviceId(), payload)
            configRepository.markSyncOk(config.withDeviceId(), meta.contentHash, false)
            val outcome = SyncOutcome(data = merged, uploadedTasks = uploadedTasks)
            if (logOp != null) {
                logOutcome(logOp, outcome)
            } else {
                outcome
            }
        } catch (error: WebDavException) {
            if (logOp != null) {
                logOutcome(logOp, SyncOutcome(error = syncErrorMessage(error)))
            }
            throw error
        }
    }

    fun pushLocalUploadOnly(
        config: WebDavConfig = configRepository.load(),
        requireEnabled: Boolean = true,
        logOp: String = "push_upload_only",
    ): SyncOutcome {
        if (requireEnabled && !config.enabled) {
            throw WebDavException("Синхронизация WebDAV отключена")
        }
        val dataFile = taskRepository.dataFile
        if (!dataFile.isFile) {
            throw WebDavException("Локальный файл данных не найден")
        }

        return try {
            val client = WebDavClient(config.withDeviceId())
            var conflictDetected = false
            val localPayload = dataFile.readBytes()
            val localHash = contentHash(localPayload)
            var downloadedTasks = 0

            if (client.exists()) {
                val remotePayload = client.download()
                downloadedTasks = WebDavSyncLog.countTasksInPayload(remotePayload)
                val remoteMeta = readRemoteMeta(client, config)
                val remoteHash = remotePayloadHash(remotePayload, remoteMeta)
                if (remoteChangedSinceSync(config, remoteHash, localHash)) {
                    conflictDetected = true
                }
            }

            val uploadedTasks = WebDavSyncLog.countTasksInPayload(localPayload)
            val meta = uploadPayload(client, config.withDeviceId(), localPayload)
            configRepository.markSyncOk(config.withDeviceId(), meta.contentHash, conflictDetected)

            val notice = if (conflictDetected) {
                "При выходе на сервер отправлена локальная копия без слияния; " +
                    "в облаке была более новая версия."
            } else {
                ""
            }
            logOutcome(
                logOp,
                SyncOutcome(
                    conflictDetected = conflictDetected,
                    notice = notice,
                    uploadedTasks = uploadedTasks,
                    downloadedTasks = downloadedTasks,
                ),
            )
        } catch (error: WebDavException) {
            logOutcome(logOp, SyncOutcome(error = syncErrorMessage(error)))
            throw error
        }
    }

    private fun finalizeMergedState(merged: AppDataDto): AppDataDto {
        val prepared = TaskRepository.prepareLoadedData(merged)
        taskRepository.save(prepared)
        return prepared
    }

    private fun readRemoteMeta(client: WebDavClient, config: WebDavConfig): RemoteSyncMeta? {
        val metaUrl = config.metaRemoteUrl()
        if (!client.exists(metaUrl)) {
            return null
        }
        return runCatching {
            parseMetaBytes(client.download(metaUrl))
        }.getOrNull()
    }

    private fun remoteChangedSinceSync(
        config: WebDavConfig,
        remoteHash: String,
        localHash: String,
    ): Boolean {
        if (config.lastRemoteContentHash.isNotBlank()) {
            return remoteHash != config.lastRemoteContentHash
        }
        return localHash.isNotEmpty() && remoteHash != localHash
    }

    private fun uploadPayload(
        client: WebDavClient,
        config: WebDavConfig,
        payload: ByteArray,
    ): RemoteSyncMeta {
        val dataUrl = config.remoteUrl()
        val metaUrl = config.metaRemoteUrl()
        val deviceId = config.withDeviceId().deviceId
        val meta = newMeta(payload, deviceId)
        val metaBytes = metaToBytes(meta)
        var lastError: WebDavException? = null
        repeat(FULL_UPLOAD_CYCLES) { cycle ->
            try {
                client.upload(dataUrl, payload)
                uploadMetaWithRetries(client, metaUrl, metaBytes)
                return meta
            } catch (error: WebDavException) {
                lastError = error
                if (cycle < FULL_UPLOAD_CYCLES - 1) {
                    Thread.sleep(500L * (cycle + 1))
                }
            }
        }
        throw WebDavException(
            "Не удалось загрузить data.json и sync-meta после $FULL_UPLOAD_CYCLES циклов: $lastError",
        )
    }

    private fun uploadMetaWithRetries(
        client: WebDavClient,
        metaUrl: String,
        metaBytes: ByteArray,
    ) {
        var lastError: WebDavException? = null
        repeat(META_UPLOAD_ATTEMPTS) { attempt ->
            try {
                client.upload(metaUrl, metaBytes)
                return
            } catch (error: WebDavException) {
                lastError = error
                if (attempt < META_UPLOAD_ATTEMPTS - 1) {
                    Thread.sleep(500L * (attempt + 1))
                }
            }
        }
        throw lastError ?: WebDavException("Не удалось загрузить sync-meta")
    }

    private fun syncErrorMessage(error: Throwable): String {
        return when (error) {
            is WebDavException -> error.message ?: "Ошибка WebDAV"
            is IllegalArgumentException -> error.message ?: "Ошибка данных"
            else -> error.message ?: error.javaClass.simpleName
        }
    }

    companion object {
        private const val META_UPLOAD_ATTEMPTS = 3
        private const val FULL_UPLOAD_CYCLES = 2
    }
}
