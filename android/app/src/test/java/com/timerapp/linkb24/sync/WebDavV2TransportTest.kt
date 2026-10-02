package com.timerapp.linkb24.sync

import com.timerapp.linkb24.data.*
import com.timerapp.linkb24.webdav.*
import java.net.InetAddress
import java.nio.file.Files
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlinx.serialization.json.*
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.Assert.*
import org.junit.Test

class WebDavV2TransportTest {
    @Test(timeout = 30_000) fun preconditionRetryMergesRemoteAndPreservesLocalEditDuringPut() {
        val dir = Files.createTempDirectory("webdav-v2").toFile()
        val server = MockWebServer()
        val serverFailure = AtomicReference<Throwable?>()
        try {
            val repository = TaskRepository(File(dir, "data.json"))
            repository.save(AppDataDto(tasks = listOf(TaskDto("t", "2026-01-01", "initial", createdAt = "2026-01-01T09:00:00Z"))))
            var remote = repository.syncSnapshot().document
            var puts = 0
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse = try {
                    when {
                        request.path != "/tasks.json.v2.json" -> MockResponse().setResponseCode(404)
                        request.method == "GET" -> MockResponse().setBody(remote.toString())
                            .setHeader("ETag", if (puts == 0) "\"one\"" else "\"two\"")
                        request.method == "PUT" -> {
                            if (puts++ == 0) {
                                remote = SyncV2.change(remote, "desktop", JsonArray(listOf(JsonPrimitive("task"), JsonPrimitive("t"))),
                                    buildJsonObject { put("description", "remote") })
                                MockResponse().setResponseCode(412)
                            } else {
                                remote = Json.parseToJsonElement(request.body.clone().readUtf8()).jsonObject
                                repository.mutate { it.copy(tasks = it.tasks.map { task -> task.copy(title = "typed during PUT") }) }
                                MockResponse().setResponseCode(204)
                            }
                        }
                        else -> MockResponse().setResponseCode(405)
                    }
                } catch (error: Throwable) {
                    serverFailure.compareAndSet(null, error)
                    MockResponse().setResponseCode(500)
                }
            }
            server.start(InetAddress.getByName("127.0.0.1"), 0)
            val config = WebDavConfig(enabled = true, url = "http://127.0.0.1:${server.port}", username = "test", remotePath = "tasks.json")
            val result = WebDavSync(repository, WebDavConfigRepository(File(dir, "config.json")),
                clientFactory = { WebDavClient(it, timeoutMs = 2_000, allowInsecureLoopbackForTests = true) }).syncNow(config)
            serverFailure.get()?.let { throw it }
            assertEquals("", result.error)
            assertEquals(4, server.requestCount)
            val requests = List(4) { server.takeRequest(1, TimeUnit.SECONDS) ?: error("Missing recorded request") }
            assertEquals(listOf("GET", "PUT", "GET", "PUT"), requests.map { it.method })
            assertTrue(requests.all { it.path == "/tasks.json.v2.json" })
            assertEquals("\"one\"", requests[1].getHeader("If-Match"))
            assertEquals("\"two\"", requests[3].getHeader("If-Match"))
            assertNull(requests[1].getHeader("If-None-Match"))
            assertNull(requests[3].getHeader("If-None-Match"))
            val uploaded = SyncV2.validate(Json.parseToJsonElement(requests[3].body.readUtf8()).jsonObject)
            assertEquals("remote", SyncV2.tasks(uploaded).single().jsonObject.getValue("description").jsonPrimitive.content)
            assertEquals("initial", SyncV2.tasks(uploaded).single().jsonObject.getValue("title").jsonPrimitive.content)
            assertEquals("typed during PUT", repository.load().tasks.single().title)
            assertEquals("remote", repository.load().tasks.single().description)
        } finally {
            try { server.shutdown() } finally { dir.deleteRecursively() }
        }
    }

    @Test(timeout = 15_000) fun missingStrongEtagStopsBeforePut() {
        for (etag in listOf<String?>("W/\"weak\"", null)) {
            val server = MockWebServer()
            try {
                server.dispatcher = object : Dispatcher() {
                    override fun dispatch(request: RecordedRequest): MockResponse {
                        val response = MockResponse().setBody(SyncV2.empty().toString())
                        if (etag != null) response.setHeader("ETag", etag)
                        return response
                    }
                }
                server.start(InetAddress.getByName("127.0.0.1"), 0)
                val config = WebDavConfig(url = "http://127.0.0.1:${server.port}", username = "test", remotePath = "tasks.json")
                assertThrows(WebDavException::class.java) {
                    WebDavClient(config, timeoutMs = 2_000, allowInsecureLoopbackForTests = true)
                        .downloadVersioned(config.remoteUrl() + ".v2.json")
                }
                assertEquals(1, server.requestCount)
                val request = server.takeRequest(1, TimeUnit.SECONDS) ?: error("Missing recorded GET")
                assertEquals("GET", request.method)
                assertEquals("/tasks.json.v2.json", request.path)
            } finally { server.shutdown() }
        }
    }
}
