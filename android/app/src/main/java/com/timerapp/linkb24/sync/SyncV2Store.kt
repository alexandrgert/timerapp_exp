package com.timerapp.linkb24.sync

import com.timerapp.linkb24.data.*
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import kotlinx.serialization.json.*

/** One authoritative JSON file: projection, causal log, local actor, UI and migration marker. */
class SyncV2Store(private val file: File) {
    data class Snapshot(val data: AppDataDto, val document: JsonObject)
    private val json = Json(AppJson) { explicitNulls = true }
    private data class State(val root: JsonObject, val actor: String, val doc: JsonObject)
    companion object { private val locks = ConcurrentHashMap<String, Any>() }
    private fun <T> locked(block: () -> T): T = synchronized(locks.getOrPut(file.canonicalPath) { Any() }) {
        file.parentFile?.mkdirs()
        RandomAccessFile(File(file.parentFile, "${file.name}.lock"), "rw").use { lockFile -> lockFile.channel.lock().use { block() } }
    }
    private fun read(): State {
        val root = if(file.isFile) {
            require(file.length() <= SyncV2.MAX_BYTES * 3L) { "Локальные данные слишком велики" }
            json.parseToJsonElement(SyncV2.decodeUtf8(file.readBytes())).jsonObject
        } else buildJsonObject { put("tasks",JsonArray(emptyList())); put("ui",json.encodeToJsonElement(UiSettingsDto.serializer(),UiSettingsDto())) }
        val existing=root["_sync_v2"]
        if(existing!=null) {
            val actor=root["_sync_actor"]?.jsonPrimitive?.content ?: error("Отсутствует локальный идентификатор синхронизации")
            return State(root,actor,SyncV2.validate(existing.jsonObject))
        }
        require(root.keys.none { it in setOf("format", "version", "schemaVersion", "sync_v2", "syncDocument") }) { "Неподдерживаемый локальный формат данных" }
        if(file.isFile)backupOnce(File(file.parentFile,"${file.name}.pre-v2.bak"),file.readBytes())
        val tasks=root["tasks"] as? JsonArray ?: error("Некорректный список задач")
        return State(root,UUID.randomUUID().toString(),SyncV2.importLegacy(tasks,"migration-${UUID.randomUUID()}"))
    }
    private fun strictInstant(value: String): java.time.Instant? = runCatching {
        java.time.OffsetDateTime.parse(value, java.time.format.DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant()
    }.getOrElse { runCatching { java.time.LocalDateTime.parse(value, java.time.format.DateTimeFormatter.ISO_LOCAL_DATE_TIME).atZone(java.time.ZoneId.systemDefault()).toInstant() }.getOrNull() }
    private fun data(state: State): AppDataDto {
        val raw=JsonObject(mapOf("tasks" to SyncV2.tasks(state.doc),"ui" to (state.root["ui"] ?: JsonObject(emptyMap()))))
        val result = json.decodeFromJsonElement(AppDataDto.serializer(),raw).copy(syncConflicts=SyncV2.project(state.doc).conflicts)
        raw.getValue("tasks").jsonArray.forEach { item ->
            val task = item.jsonObject
            java.time.LocalDate.parse(task.getValue("day").jsonPrimitive.content)
            for (field in listOf("created_at", "completed_at")) task[field]?.takeIf { it != JsonNull }?.let { require(strictInstant(it.jsonPrimitive.content) != null) { "Некорректная дата задачи в синхронизации" } }
        }
        result.tasks.forEach { task ->
            require(task.title.isNotBlank()) { "Синхронизация содержит задачу без названия" }
            task.sessions.forEach { session ->
                val start = strictInstant(session.startedAt) ?: error("Синхронизация содержит некорректное начало сессии")
                session.endedAt?.let { value -> val end = strictInstant(value) ?: error("Синхронизация содержит некорректное окончание сессии"); require(!end.isBefore(start)) { "Окончание сессии раньше начала" } }
            }
        }
        return result.copy(tasks = result.tasks.map { task ->
            when {
                task.sessions.any { it.endedAt == null } -> task.copy(status = TaskStatus.RUNNING)
                task.status == TaskStatus.RUNNING -> task.copy(status = TaskStatus.PAUSED)
                else -> task
            }
        })
    }
    private fun tasks(data: AppDataDto)=json.encodeToJsonElement(AppDataDto.serializer(),data).jsonObject.getValue("tasks").jsonArray
    private fun commit(state: State, backupPrevious: Boolean = true): Snapshot {
        val projected=SyncV2.tasks(state.doc)
        val root=JsonObject(state.root+mapOf("tasks" to projected,"_sync_v2" to state.doc,"_sync_actor" to JsonPrimitive(state.actor)))
        // Validate the app projection before replacing anything on disk.
        val ready=data(state)
        if (backupPrevious && file.isFile) atomicWrite(File(file.parentFile,"${file.name}.bak"), file.readBytes())
        atomicWrite(file,json.encodeToString(JsonObject.serializer(),root).toByteArray())
        return Snapshot(ready,state.doc)
    }
    fun load(): AppDataDto=locked {
        val state=read(); val before=data(state); val prepared=TaskRepository.prepareLoadedData(before)
        if(prepared!=before || "_sync_v2" !in state.root) persistEdit(state,before,prepared).data else before
    }
    fun bootstrap(initial: AppDataDto): AppDataDto=locked {
        val state=read()
        require(state.doc.getValue("ops").jsonArray.isEmpty()) { "Для существующих данных используйте транзакционную правку или явное восстановление копии." }
        persistEdit(state,data(state),initial).data
    }
    fun mutate(transform: (AppDataDto)->AppDataDto): AppDataDto=locked {
        val state=read();val before=data(state)
        val updated=transform(before)
        persistEdit(state,before,TaskRepository.prepareLoadedData(updated)).data
    }
    private fun persistEdit(state: State,before: AppDataDto,after: AppDataDto): Snapshot {
        val delta = SyncV2.reconcile(SyncV2.empty(), tasks(before), tasks(after), "local-change-probe")
        for (op in delta.getValue("ops").jsonArray) {
            val row = op.jsonObject
            require(before.syncConflicts.none { conflict -> conflict.entity == row["entity"] && conflict.field in row.getValue("changes").jsonObject }) {
                "Сначала выберите сохранённый вариант конфликтующего поля."
            }
        }
        val doc=SyncV2.reconcile(state.doc,tasks(before),tasks(after),state.actor)
        return commit(state.copy(doc=doc,root=JsonObject(state.root+("ui" to json.encodeToJsonElement(UiSettingsDto.serializer(),after.ui)))))
    }
    fun snapshot(): Snapshot=locked { val state=read(); if("_sync_v2" !in state.root)commit(state) else Snapshot(data(state),state.doc) }
    fun needsLegacy(source: String): Boolean=locked { source !in (read().root["_sync_legacy_sources"] as? JsonObject ?: JsonObject(emptyMap())) }
    fun merge(remote: JsonObject,legacy: ByteArray?,source: String): Snapshot=locked {
        var state=read();var doc=SyncV2.merge(state.doc,remote)
        val sources=(state.root["_sync_legacy_sources"] as? JsonObject ?: JsonObject(emptyMap())).toMutableMap()
        if(source !in sources) {
            if(legacy!=null) {
                require(legacy.size<=SyncV2.MAX_BYTES) { "Старый файл WebDAV слишком велик" }
                val raw=json.parseToJsonElement(SyncV2.decodeUtf8(legacy)).jsonObject
                require(raw.keys.none { it in setOf("format", "version", "schemaVersion", "_sync_v2", "sync_v2", "syncDocument") }) { "Неподдерживаемый формат старого файла WebDAV" }
                val schema=(raw["ui"] as? JsonObject)?.get("schema_version")?.jsonPrimitive?.intOrNull
                require(schema==null || schema in 1..2) { "Неподдерживаемая версия старого файла WebDAV" }
                val legacyTasks=raw["tasks"] as? JsonArray ?: error("Старый файл WebDAV не содержит задач")
                doc=SyncV2.merge(doc,SyncV2.importLegacy(legacyTasks,"migration-${UUID.randomUUID()}"))
                backupOnce(File(file.parentFile,"${file.name}.legacy-$source.bak"), JsonObject(mapOf("tasks" to legacyTasks)).toString().toByteArray())
            }
            sources[source]=JsonPrimitive(true)
        }
        state=state.copy(doc=doc,root=JsonObject(state.root+("_sync_legacy_sources" to JsonObject(sources))))
        commit(state)
    }
    fun resolve(conflict: SyncV2.Conflict,value: JsonElement): AppDataDto=locked {
        val state=read()
        require(SyncV2.project(state.doc).conflicts.firstOrNull { it.entity==conflict.entity && it.field==conflict.field } == conflict) { "Список вариантов изменился. Обновите конфликты и выберите снова." }
        commit(state.copy(doc=SyncV2.resolve(state.doc,state.actor,conflict.entity,conflict.field,value))).data
    }
    /** Called only by explicit backup restore; never reuse a restored installation's actor. */
    fun restore(backup: JsonObject): AppDataDto=locked {
        if (file.isFile) backupOnce(File(file.parentFile,"${file.name}.before-restore-${UUID.randomUUID()}.bak"),file.readBytes())
        val doc=backup["_sync_v2"]?.jsonObject?.let(SyncV2::validate) ?: run {
            require(backup.keys.none { it in setOf("format", "version", "schemaVersion", "sync_v2", "syncDocument") }) { "Неподдерживаемый формат резервной копии" }
            SyncV2.importLegacy(backup.getValue("tasks").jsonArray,"migration-${UUID.randomUUID()}")
        }
        commit(State(JsonObject(backup-"_sync_actor"-"_sync_legacy_sources"),UUID.randomUUID().toString(),doc), backupPrevious=false).data
    }
    private fun backupOnce(target: File,bytes: ByteArray) { if(!target.exists())atomicWrite(target,bytes) }
    private fun atomicWrite(target: File,bytes: ByteArray) {
        val temp=File(target.parentFile,".${target.name}.${UUID.randomUUID()}.tmp")
        try { FileOutputStream(temp).use { it.write(bytes);it.fd.sync() }; Files.move(temp.toPath(),target.toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING) }
        finally { temp.delete() }
    }
}
