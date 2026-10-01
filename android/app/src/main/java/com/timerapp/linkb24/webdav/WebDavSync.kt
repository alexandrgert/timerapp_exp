package com.timerapp.linkb24.webdav

import com.timerapp.linkb24.data.*
import com.timerapp.linkb24.sync.SyncV2
import kotlinx.serialization.json.*

data class SyncOutcome(val data: AppDataDto? = null, val error: String = "", val conflictDetected: Boolean = false,
    val notice: String = "", val uploadedTasks: Int = 0, val downloadedTasks: Int = 0)
data class RemoteCheckOutcome(val remoteChanged: Boolean = false, val remoteHash: String = "", val error: String = "")

/** Every entry point uses v2 compare-and-swap; legacy upload-only mode cannot bypass merge. */
class WebDavSync(
    private val taskRepository: TaskRepository,
    private val configRepository: WebDavConfigRepository,
    private val syncLog: WebDavSyncLog = WebDavSyncLog(java.io.File(taskRepository.dataFile.parentFile, WebDavSyncLog.LOG_FILENAME)),
    private val clientFactory: (WebDavConfig) -> WebDavClient = { WebDavClient(it) },
) {
    private fun v2Url(config: WebDavConfig): String {
        require(config.remotePath.isNotBlank() && config.remotePath.none { it == '?' || it == '#' }) { "Некорректный путь WebDAV" }
        return config.remoteUrl() + ".v2.json"
    }
    private fun source(config: WebDavConfig) = contentHash((config.remoteUrl()+"\n"+config.username).toByteArray())
    private fun parse(bytes: ByteArray) = SyncV2.validate(AppJson.parseToJsonElement(SyncV2.decodeUtf8(bytes)).jsonObject)
    fun syncOnStartup(): SyncOutcome { val c=configRepository.load();return if(c.enabled && c.syncOnStartup) syncNow(c,true) else SyncOutcome() }
    fun syncOnShutdown(): SyncOutcome { val c=configRepository.load();return if(c.enabled && c.syncOnShutdown) syncNow(c,true) else SyncOutcome() }
    fun syncOnReconnect(): SyncOutcome { val c=configRepository.load();return if(c.enabled && c.isConfigured()) syncNow(c,true) else SyncOutcome() }
    fun checkRemoteOnPeriodic(): RemoteCheckOutcome { val c=configRepository.load();return if(c.periodicSyncEnabled())checkRemoteChanges(c,true) else RemoteCheckOutcome() }
    fun checkRemoteChanges(config: WebDavConfig=configRepository.load(),requireEnabled: Boolean=true): RemoteCheckOutcome {
        if(requireEnabled && !config.enabled)return RemoteCheckOutcome()
        return runCatching {
            val remote=clientFactory(config).downloadVersioned(v2Url(config))
            if(remote.payload==null) RemoteCheckOutcome(remoteChanged=taskRepository.needsLegacyImport(source(config)))
            else { parse(remote.payload);val hash=contentHash(remote.payload);RemoteCheckOutcome(hash!=config.lastRemoteContentHash,hash) }
        }.getOrElse { RemoteCheckOutcome(error=message(it)) }
    }
    fun syncNow(config: WebDavConfig=configRepository.load(),requireEnabled: Boolean=false): SyncOutcome =
        runCatching { exchange(config,requireEnabled,"sync",true) }.getOrElse { error ->
            val text=message(error);configRepository.markSyncError(config,text);SyncOutcome(error=text)
        }
    fun pullAndMerge(config: WebDavConfig=configRepository.load(),requireEnabled: Boolean=true,logOp: String="pull") = exchange(config,requireEnabled,logOp,false)
    fun pushLocal(config: WebDavConfig=configRepository.load(),requireEnabled: Boolean=true,logOp: String="push") = exchange(config,requireEnabled,logOp,true)
    fun pushMerged(config: WebDavConfig=configRepository.load(),requireEnabled: Boolean=true,logOp: String?=null) = exchange(config,requireEnabled,logOp ?: "push",true)
    fun pushLocalUploadOnly(config: WebDavConfig=configRepository.load(),requireEnabled: Boolean=true,logOp: String="push_upload_only") = exchange(config,requireEnabled,logOp,true)

    private fun exchange(config: WebDavConfig,requireEnabled: Boolean,op: String,upload: Boolean): SyncOutcome {
        if(requireEnabled && !config.enabled)throw WebDavException("Синхронизация WebDAV отключена")
        if(!config.isConfigured())throw WebDavException("WebDAV не настроен")
        try {
            val client=clientFactory(config);val url=v2Url(config);val source=source(config)
            // Network outside the local lock. Legacy is imported independently only once.
            repeat(3) { attempt ->
                val remote=client.downloadVersioned(url)
                val document=remote.payload?.let(::parse) ?: SyncV2.empty()
                val legacy=if(remote.payload==null && taskRepository.needsLegacyImport(source))client.downloadVersioned(config.remoteUrl(),false).payload else null
                val merged=taskRepository.mergeSync(document,legacy,source)
                val payload=SyncV2.canonical(merged.document).toByteArray(Charsets.UTF_8)
                if(upload)try { client.uploadVersioned(url,payload,remote.etag) }
                catch(error: WebDavException) { if(error.statusCode==412 && attempt<2)return@repeat;throw error }
                // Local edits made during PUT remain on disk; never replace them with sent snapshot.
                val latest=taskRepository.syncSnapshot();val conflicts=latest.data.syncConflicts.isNotEmpty() || latest.data.tasks.sumOf { t->t.sessions.count { it.endedAt==null } }>1
                val hash=if(upload)contentHash(payload) else remote.payload?.let(::contentHash).orEmpty()
                configRepository.markSyncOk(config,hash,conflicts)
                val notice=if(conflicts) "Сохранены конфликтующие изменения. Выберите варианты в списке задач." else "Синхронизация WebDAV v2 завершена"
                val outcome=SyncOutcome(latest.data,conflictDetected=conflicts,notice=notice,uploadedTasks=if(upload)merged.data.tasks.size else 0,downloadedTasks=SyncV2.tasks(document).size)
                syncLog.append(op,outcome.uploadedTasks,outcome.downloadedTasks,true,"")
                return outcome
            }
            throw WebDavException("Файл изменялся одновременно. Повторите синхронизацию.")
        }catch(error: Exception){syncLog.append(op,0,0,false,message(error));throw error}
    }
    private fun message(error: Throwable)=when(error){is WebDavException,is IllegalArgumentException,is IllegalStateException->error.message ?: "Ошибка данных WebDAV";else->"Не удалось синхронизировать WebDAV"}
}
