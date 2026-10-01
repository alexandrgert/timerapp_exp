package com.timerapp.linkb24.sync

import com.timerapp.linkb24.data.*
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import java.nio.file.Files
import java.io.File

class SyncV2Test {
    private fun entity(vararg ids:String)=JsonArray(ids.map(::JsonPrimitive))
    private fun task()=TaskDto("task","2026-01-01","Задача",createdAt="2026-01-01T09:00:00Z",sessions=listOf(SessionDto("session","2026-01-01T10:00:00Z","2026-01-01T11:00:00Z",comment="old")))
    @Test fun sharedCrossPlatformFixtures() {
        val input=requireNotNull(javaClass.classLoader?.getResourceAsStream("sync-v2/cases.json"))
        val fixtures=input.bufferedReader().use { Json.parseToJsonElement(it.readText()).jsonArray }
        for(item in fixtures) {
            val f=item.jsonObject;val merged=SyncV2.merge(f.getValue("left").jsonObject,f.getValue("right").jsonObject)
            assertTrue(f["name"].toString(),SyncV2.equal(merged,SyncV2.merge(f.getValue("right").jsonObject,f.getValue("left").jsonObject)))
            val projection=SyncV2.project(merged);val target=f["entity"] ?: entity("task","t")
            val selected=projection.entities.first { it.entity==target }
            (f["expectedFields"] as? JsonObject)?.forEach { (field,value)->assertTrue("${f["name"]}:$field",SyncV2.equal(value,selected.values.getValue(field))) }
            f["expectedDeleted"]?.let { assertEquals(it.jsonPrimitive.boolean,selected.deleted) }
            val fields=projection.conflicts.filter { it.entity==target }.map { it.field }.sorted()
            assertEquals(f["name"].toString(),f.getValue("expectedConflictFields").jsonArray.map { it.jsonPrimitive.content }.sorted(),fields)
        }
    }
    @Test fun migrationIsAtomicAndPreservesUnknownMetadataAndFreshMutations() {
        val dir=Files.createTempDirectory("sync-v2").toFile()
        try {
            val file=File(dir,"data.json")
            val raw=AppJson.encodeToJsonElement(AppDataDto.serializer(),AppDataDto(tasks=listOf(task()))).jsonObject
            val t=raw.getValue("tasks").jsonArray.first().jsonObject
            file.writeText(JsonObject(raw+("tasks" to JsonArray(listOf(JsonObject(t+("future_field" to JsonPrimitive("keep"))))))).toString())
            val untouched=file.readBytes();val a=TaskRepository(file);val b=TaskRepository(file)
            a.load();assertArrayEquals(untouched,File(dir,"data.json.pre-v2.bak").readBytes())
            b.mutate { it.copy(tasks=it.tasks.map { t->t.copy(description="remote") }) }
            a.mutate { it.copy(tasks=it.tasks.map { t->t.copy(title="local") }) }
            val loaded=b.load().tasks.single();assertEquals("local",loaded.title);assertEquals("remote",loaded.description)
            assertEquals(JsonPrimitive("keep"),SyncV2.tasks(a.syncSnapshot().document).first().jsonObject["future_field"])
            assertEquals("local",Json.parseToJsonElement(file.readText()).jsonObject.getValue("tasks").jsonArray.first().jsonObject.getValue("title").jsonPrimitive.content)
        }finally { dir.deleteRecursively() }
    }
    @Test fun legacyAgainstDeletionRemainsAConflictAndImportsOnlyOnce() {
        val dir=Files.createTempDirectory("sync-v2").toFile()
        try {
            val repository=TaskRepository(File(dir,"data.json"));repository.save(AppDataDto(tasks=listOf(task())))
            val remote=SyncV2.change(repository.syncSnapshot().document,"desktop",entity("task","task"),buildJsonObject { put("\$alive",false) })
            val legacy=AppJson.encodeToString(AppDataDto.serializer(),AppDataDto(tasks=listOf(task()))).toByteArray()
            val first=repository.mergeSync(remote,legacy,"endpoint");assertTrue(first.data.tasks.isEmpty());assertTrue(first.data.syncConflicts.any { it.field=="\$alive" })
            val again=repository.mergeSync(remote,legacy,"endpoint");assertEquals(first.document.getValue("ops").jsonArray.size,again.document.getValue("ops").jsonArray.size)
        }finally { dir.deleteRecursively() }
    }
    @Test fun staleCommentFormKeepsNewIntervalAndRejectsSameFieldOverwrite() {
        val repository=TaskRepository(File("unused"));val original=task().sessions.single()
        val fresh=AppDataDto(tasks=listOf(task().copy(sessions=listOf(original.copy(endedAt="2026-01-01T10:40:00Z")))))
        val updated=repository.updateSessionFromSnapshot("task",fresh,original,original.startedAt,original.endedAt,"new")
        assertEquals("2026-01-01T10:40:00Z",updated.tasks.single().sessions.single().endedAt)
        val other=fresh.copy(tasks=listOf(fresh.tasks.single().copy(sessions=listOf(fresh.tasks.single().sessions.single().copy(comment="other")))))
        assertThrows(IllegalArgumentException::class.java) { repository.updateSessionFromSnapshot("task",other,original,original.startedAt,original.endedAt,"new") }
    }
    @Test fun concurrentTimersAreNotNormalizedAway() {
        val a=task().copy(status=TaskStatus.RUNNING,sessions=listOf(task().sessions.single().copy(endedAt=null)))
        val data=AppDataDto(tasks=listOf(a,a.copy(id="other")))
        assertEquals(data,TaskRepository.prepareLoadedData(data))
    }
    @Test fun staleConflictChoiceDoesNotDiscardUnseenCandidate() {
        val dir=Files.createTempDirectory("sync-v2-conflict").toFile()
        try {
            val repository=TaskRepository(File(dir,"data.json"));repository.save(AppDataDto(tasks=listOf(task())))
            val seed=repository.syncSnapshot().document
            val a=SyncV2.change(seed,"a",entity("task","task"),buildJsonObject { put("title","A") })
            val b=SyncV2.change(seed,"b",entity("task","task"),buildJsonObject { put("title","B") })
            val first=repository.mergeSync(SyncV2.merge(a,b),null,"target")
            val displayed=first.data.syncConflicts.single { it.field=="title" }
            val c=SyncV2.change(seed,"c",entity("task","task"),buildJsonObject { put("title","C") })
            repository.mergeSync(c,null,"target")
            assertThrows(IllegalArgumentException::class.java) { repository.resolveSync(displayed,displayed.candidates.first().value) }
            assertEquals(3,repository.load().syncConflicts.single { it.field=="title" }.candidates.size)
        } finally { dir.deleteRecursively() }
    }
    @Test fun invalidProjectedDateIsRejectedBeforeDiskChanges() {
        val dir=Files.createTempDirectory("sync-v2-invalid").toFile()
        try {
            val file=File(dir,"data.json");val repository=TaskRepository(file)
            repository.save(AppDataDto(tasks=listOf(task())))
            val remote=SyncV2.change(repository.syncSnapshot().document,"other",entity("task","task"),buildJsonObject { put("day","not-a-date") })
            val before=file.readBytes()
            assertThrows(Exception::class.java) { repository.mergeSync(remote,null,"target") }
            assertArrayEquals(before,file.readBytes())
        } finally { dir.deleteRecursively() }
    }
    @Test fun malformedUtf8IsNotSilentlyReplaced() {
        assertThrows(IllegalArgumentException::class.java) { SyncV2.decodeUtf8(byteArrayOf(0xc3.toByte(),0x28)) }
    }

}
