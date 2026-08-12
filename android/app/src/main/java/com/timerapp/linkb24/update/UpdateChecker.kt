package com.timerapp.linkb24.update

import com.timerapp.linkb24.BuildConfig
import com.timerapp.linkb24.data.DEFAULT_UPDATE_GITHUB_REPO
import com.timerapp.linkb24.data.normalizeGithubRepo
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.net.HttpURLConnection
import java.net.URL

data class LatestRelease(
    val tagName: String,
    val version: String,
    val htmlUrl: String,
)

data class UpdateCheckResult(
    val ok: Boolean,
    val error: String = "",
    val currentVersion: String = "",
    val latest: LatestRelease? = null,
    val updateAvailable: Boolean = false,
    val githubRepo: String = DEFAULT_UPDATE_GITHUB_REPO,
)

object UpdateChecker {
    private val json = Json { ignoreUnknownKeys = true }

    fun latestReleaseApiUrl(repo: String = DEFAULT_UPDATE_GITHUB_REPO): String {
        val normalized = normalizeGithubRepo(repo)
        return "https://api.github.com/repos/$normalized/releases/latest"
    }

    fun normalizeVersion(tagOrVersion: String): String {
        val text = tagOrVersion.trim()
        val match = Regex("""^v?(\d+(?:\.\d+)*)""", RegexOption.IGNORE_CASE).find(text)
        return match?.groupValues?.get(1) ?: text.trimStart('v', 'V')
    }

    fun versionTuple(version: String): List<Int> {
        return normalizeVersion(version)
            .split('.')
            .mapNotNull { part -> part.toIntOrNull() }
            .ifEmpty { listOf(0) }
    }

    fun isNewer(current: String, remote: String): Boolean {
        val left = versionTuple(current)
        val right = versionTuple(remote)
        val size = maxOf(left.size, right.size)
        for (index in 0 until size) {
            val a = left.getOrElse(index) { 0 }
            val b = right.getOrElse(index) { 0 }
            if (b != a) {
                return b > a
            }
        }
        return false
    }

    fun parseLatestRelease(
        payload: String,
        githubRepo: String = DEFAULT_UPDATE_GITHUB_REPO,
    ): LatestRelease {
        val root = json.parseToJsonElement(payload).jsonObject
        val tagName = root["tag_name"]?.jsonPrimitive?.content?.trim().orEmpty()
        val version = normalizeVersion(tagName)
        require(tagName.isNotEmpty() && version.isNotEmpty()) { "Некорректный ответ GitHub Releases" }
        val repo = normalizeGithubRepo(githubRepo)
        var htmlUrl = root["html_url"]?.jsonPrimitive?.content?.trim().orEmpty()
        if (htmlUrl.isEmpty()) {
            htmlUrl = "https://github.com/$repo/releases/tag/$tagName"
        }
        return LatestRelease(tagName = tagName, version = version, htmlUrl = htmlUrl)
    }

    fun fetchLatestRelease(
        githubRepo: String = DEFAULT_UPDATE_GITHUB_REPO,
        url: String? = null,
        currentVersion: String = BuildConfig.VERSION_NAME,
    ): LatestRelease {
        val repo = normalizeGithubRepo(githubRepo)
        val requestUrl = url ?: latestReleaseApiUrl(repo)
        val connection = (URL(requestUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "timerapp-exp/${normalizeVersion(currentVersion)}")
            connectTimeout = 10_000
            readTimeout = 10_000
        }
        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                throw IllegalStateException("HTTP $code: $body")
            }
            return parseLatestRelease(body, githubRepo = repo)
        } finally {
            connection.disconnect()
        }
    }

    fun checkForUpdate(
        currentVersion: String = BuildConfig.VERSION_NAME,
        dismissedVersion: String = "",
        respectDismissed: Boolean = true,
        githubRepo: String = DEFAULT_UPDATE_GITHUB_REPO,
        fetch: () -> LatestRelease = {
            fetchLatestRelease(githubRepo = githubRepo, currentVersion = currentVersion)
        },
    ): UpdateCheckResult {
        val current = normalizeVersion(currentVersion)
        val repo = normalizeGithubRepo(githubRepo)
        return try {
            val latest = fetch()
            var available = isNewer(current, latest.version)
            if (respectDismissed && available && normalizeVersion(dismissedVersion) == latest.version) {
                available = false
            }
            UpdateCheckResult(
                ok = true,
                currentVersion = current,
                latest = latest,
                updateAvailable = available,
                githubRepo = repo,
            )
        } catch (error: Exception) {
            UpdateCheckResult(
                ok = false,
                error = error.message ?: error.toString(),
                currentVersion = current,
                githubRepo = repo,
            )
        }
    }
}
