package com.timerapp.linkb24.sync

import com.timerapp.linkb24.data.*
import com.timerapp.linkb24.webdav.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.nio.file.Files
import java.io.File
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class WebDavV2TransportTest {
    @Test fun preconditionRetryMergesRemoteAndPreservesLocalEditDuringPut() {
        val dir=Files.createTempDirectory("webdav-v2").toFile()
        val server=HttpServer.create(InetSocketAddress("127.0.0.1",0),0)
        try {
            val repository=TaskRepository(File(dir,"data.json"))
            repository.save(AppDataDto(tasks=listOf(TaskDto("t","2026-01-01","initial",createdAt="2026-01-01T09:00:00Z"))))
            var remote=repository.syncSnapshot().document;var puts=0;var legacyRequests=0
            server.createContext("/tasks.json") { exchange ->
                val method=exchange.requestMethod;val path=exchange.requestURI.path
                if(path!="/tasks.json.v2.json") { legacyRequests++;exchange.sendResponseHeaders(404,-1);exchange.close();return@createContext }
                if(method=="GET") {
                    val body=remote.toString().toByteArray();exchange.responseHeaders.set("ETag",if(puts==0)"\"one\"" else "\"two\"")
                    exchange.sendResponseHeaders(200,body.size.toLong());exchange.responseBody.use { it.write(body) }
                } else if(method=="PUT") {
                    val payload=Json.parseToJsonElement(exchange.requestBody.bufferedReader().readText()).jsonObject
                    if(puts++==0) {
                        assertEquals("\"one\"",exchange.requestHeaders.getFirst("If-Match"))
                        remote=SyncV2.change(remote,"desktop",JsonArray(listOf(JsonPrimitive("task"),JsonPrimitive("t"))),buildJsonObject { put("description","remote") })
                        exchange.sendResponseHeaders(412,-1)
                    } else {
                        assertEquals("\"two\"",exchange.requestHeaders.getFirst("If-Match"));remote=payload
                        repository.mutate { it.copy(tasks=it.tasks.map { t->t.copy(title="typed during PUT") }) }
                        exchange.sendResponseHeaders(204,-1)
                    }
                    exchange.close()
                } else { exchange.sendResponseHeaders(405,-1);exchange.close() }
            }
            server.start()
            val config=WebDavConfig(enabled=true,url="http://127.0.0.1:${server.address.port}",username="test",remotePath="tasks.json")
            val result=WebDavSync(repository,WebDavConfigRepository(File(dir,"config.json")),clientFactory={ WebDavClient(it,allowInsecureLoopbackForTests=true) }).syncNow(config)
            assertEquals("",result.error);assertEquals(2,puts);assertEquals(0,legacyRequests)
            assertEquals("typed during PUT",repository.load().tasks.single().title)
            assertEquals("remote",repository.load().tasks.single().description)
        } finally { server.stop(0);dir.deleteRecursively() }
    }
    @Test fun missingStrongEtagStopsBeforePut() {
        val server=HttpServer.create(InetSocketAddress("127.0.0.1",0),0);var puts=0
        try {
            server.createContext("/") { exchange ->
                if(exchange.requestMethod=="PUT")puts++
                val body=SyncV2.empty().toString().toByteArray();exchange.responseHeaders.set("ETag","W/\"weak\"");exchange.sendResponseHeaders(200,body.size.toLong());exchange.responseBody.use { it.write(body) }
            };server.start()
            val config=WebDavConfig(url="http://127.0.0.1:${server.address.port}",username="test",remotePath="tasks.json")
            assertThrows(WebDavException::class.java) { WebDavClient(config,allowInsecureLoopbackForTests=true).downloadVersioned(config.remoteUrl()+".v2.json") }
            assertEquals(0,puts)
        } finally { server.stop(0) }
    }
}
