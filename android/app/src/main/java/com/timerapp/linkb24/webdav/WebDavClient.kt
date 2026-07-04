package com.timerapp.linkb24.webdav

import com.timerapp.linkb24.data.WebDavConfig
import java.io.IOException
import java.util.concurrent.TimeUnit
import okhttp3.Credentials
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class WebDavException(
    message: String,
    val statusCode: Int? = null,
) : Exception(message)

class WebDavClient(
    private val config: WebDavConfig,
    private val timeoutMs: Int = 60_000,
) {
    private val http = OkHttpClient.Builder()
        .connectTimeout(timeoutMs.toLong(), TimeUnit.MILLISECONDS)
        .readTimeout(timeoutMs.toLong(), TimeUnit.MILLISECONDS)
        .writeTimeout(timeoutMs.toLong(), TimeUnit.MILLISECONDS)
        .build()

    fun testConnection(): String {
        requireConfigured()
        val base = config.url.trim().trimEnd('/') + "/"
        requestVoid("HEAD", base)
        return if (exists(config.remoteUrl())) {
            "Подключение успешно (удалённый файл найден)"
        } else {
            "Подключение успешно (файл будет создан при первой синхронизации)"
        }
    }

    fun exists(url: String? = null): Boolean {
        val target = url ?: config.remoteUrl()
        return runCatching {
            requestVoid("HEAD", target)
            true
        }.getOrElse { error ->
            when (error) {
                is WebDavException -> when (error.statusCode) {
                    404 -> false
                    405, 501 -> existsViaRangeGet(target)
                    else -> throw error
                }
                else -> throw error
            }
        }
    }

    fun download(url: String? = null): ByteArray {
        return requestBytes("GET", url ?: config.remoteUrl())
    }

    fun upload(
        url: String,
        payload: ByteArray,
        contentType: String = "application/json; charset=utf-8",
    ) {
        ensureCollection(url)
        requestVoid(
            "PUT",
            url,
            body = payload,
            extraHeaders = mapOf("Content-Type" to contentType),
        )
    }

    fun ensureCollection(fileUrl: String) {
        val parent = if (fileUrl.endsWith("/")) {
            fileUrl
        } else {
            fileUrl.substringBeforeLast('/') + "/"
        }
        val base = config.url.trim().trimEnd('/') + "/"
        if (!parent.startsWith(base)) {
            return
        }
        val relative = parent.removePrefix(base).trim('/')
        if (relative.isEmpty()) {
            return
        }
        var current = base
        for (segment in relative.split('/')) {
            current = "$current$segment/"
            try {
                requestVoid("MKCOL", current)
            } catch (error: WebDavException) {
                if (error.statusCode !in MKCOL_IGNORE_CODES) {
                    throw error
                }
            }
        }
    }

    private fun existsViaRangeGet(url: String): Boolean {
        return runCatching {
            requestBytes("GET", url, extraHeaders = mapOf("Range" to "bytes=0-0"))
            true
        }.getOrElse { error ->
            when (error) {
                is WebDavException -> when (error.statusCode) {
                    404 -> false
                    200, 206, 416 -> true
                    else -> throw error
                }
                else -> throw error
            }
        }
    }

    private fun requireConfigured() {
        if (!config.isConfigured()) {
            throw WebDavException("WebDAV не настроен: укажите URL и имя пользователя")
        }
    }

    private fun requestVoid(
        method: String,
        url: String,
        body: ByteArray? = null,
        extraHeaders: Map<String, String> = emptyMap(),
    ) {
        requestBytes(method, url, body, extraHeaders)
    }

    private fun requestBytes(
        method: String,
        url: String,
        body: ByteArray? = null,
        extraHeaders: Map<String, String> = emptyMap(),
    ): ByteArray {
        val request = buildRequest(method, url, body, extraHeaders)
        try {
            http.newCall(request).execute().use { response ->
                val code = response.code
                if (code !in SUCCESS_CODES) {
                    val errorBody = response.body?.string().orEmpty()
                    throw WebDavException(
                        sanitizeError(httpErrorMessage(method, code, errorBody), config),
                        statusCode = code,
                    )
                }
                return response.body?.bytes() ?: ByteArray(0)
            }
        } catch (error: WebDavException) {
            throw error
        } catch (error: IOException) {
            throw WebDavException(
                sanitizeError("WebDAV $method: ${networkErrorHint(error)}", config),
            )
        }
    }

    private fun buildRequest(
        method: String,
        url: String,
        body: ByteArray?,
        extraHeaders: Map<String, String>,
    ): Request {
        val builder = Request.Builder()
            .url(url)
            .header("Authorization", basicAuthHeader(config.username, config.password))
            .header("User-Agent", "TaskTimer-Experiment-Android")
        val contentType = extraHeaders["Content-Type"]
        extraHeaders.forEach { (key, value) ->
            if (key != "Content-Type" || method !in setOf("PUT", "POST")) {
                builder.header(key, value)
            }
        }
        return when (method) {
            "GET" -> builder.get()
            "HEAD" -> builder.head()
            "PUT" -> builder.put(
                body!!.toRequestBody(
                    (contentType ?: "application/octet-stream").toMediaType(),
                ),
            )
            "MKCOL" -> builder.method("MKCOL", null)
            else -> builder.method(
                method,
                body?.toRequestBody(
                    (contentType ?: "application/octet-stream").toMediaType(),
                ),
            )
        }.build()
    }

    companion object {
        private val SUCCESS_CODES = setOf(200, 201, 204, 206, 207, 416)
        private val MKCOL_IGNORE_CODES = setOf(405, 409, 423)

        private fun basicAuthHeader(username: String, password: String): String {
            return Credentials.basic(username, password, Charsets.UTF_8)
        }

        private fun sanitizeError(text: String, config: WebDavConfig): String {
            var sanitized = text
            if (config.password.isNotEmpty()) {
                sanitized = sanitized.replace(config.password, "***")
            }
            if (config.url.isNotEmpty()) {
                sanitized = sanitized.replace(config.url.trim().trimEnd('/'), "***")
                sanitized = sanitized.replace(config.url, "***")
            }
            sanitized = sanitized.replace(config.remoteUrl(), "***")
            return sanitized
        }

        private fun httpErrorMessage(method: String, code: Int, body: String): String {
            val detail = body.trim().replace(Regex("<[^>]+>"), " ").replace(Regex("\\s+"), " ").trim()
                .take(160)
            val hint = when (code) {
                401 -> "Неверный логин или пароль WebDAV. " +
                    "В Облаке Билайн пароль берётся в «Профиль → Безопасность → WebDAV», " +
                    "это не пароль от аккаунта."
                403 -> "Доступ запрещён. Проверьте путь к файлу на сервере."
                404 -> "Файл не найден на сервере."
                405, 501 -> "Сервер не поддерживает метод $method."
                else -> "Ошибка сервера."
            }
            return buildString {
                append("WebDAV $method HTTP $code: $hint")
                if (detail.isNotEmpty() && !detail.contains("401 Access not authorized", ignoreCase = true)) {
                    append(" (").append(detail).append(')')
                }
            }
        }

        private fun networkErrorHint(error: IOException): String {
            val message = error.message.orEmpty()
            if (message.startsWith("http://") || message.startsWith("https://")) {
                return "не удалось получить ответ сервера"
            }
            return message.ifBlank { "сетевая ошибка" }
        }
    }
}
