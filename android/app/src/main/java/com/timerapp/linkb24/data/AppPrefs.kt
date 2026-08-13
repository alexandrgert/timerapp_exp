package com.timerapp.linkb24.data

import android.content.Context
import kotlinx.serialization.Serializable
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.time.Instant
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

const val MIN_UPDATE_CHECK_INTERVAL_DAYS = 1
const val MAX_UPDATE_CHECK_INTERVAL_DAYS = 30
const val DEFAULT_UPDATE_CHECK_INTERVAL_DAYS = 1
const val DEFAULT_UPDATE_GITHUB_REPO = "alexandrgert/timerapp_exp"

@Serializable
data class AppPrefs(
    val checkUpdates: Boolean = false,
    val updateCheckIntervalDays: Int = DEFAULT_UPDATE_CHECK_INTERVAL_DAYS,
    val updateGithubRepo: String = DEFAULT_UPDATE_GITHUB_REPO,
    val lastUpdateCheckAt: String = "",
    val dismissedUpdateVersion: String = "",
)

class AppPrefsRepository(
    private val prefsFile: File,
) {
    constructor(context: Context) : this(File(context.filesDir, "app.json"))

    fun load(): AppPrefs {
        if (!prefsFile.isFile) {
            return AppPrefs()
        }
        return runCatching {
            AppJson.decodeFromString(AppPrefs.serializer(), prefsFile.readText())
        }.getOrElse { AppPrefs() }.normalized()
    }

    fun save(prefs: AppPrefs) {
        prefsFile.parentFile?.mkdirs()
        val payload = AppJson.encodeToString(AppPrefs.serializer(), prefs.normalized())
        val tempFile = File(prefsFile.parentFile, "${prefsFile.name}.tmp")
        tempFile.writeText(payload)
        Files.move(
            tempFile.toPath(),
            prefsFile.toPath(),
            StandardCopyOption.REPLACE_EXISTING,
            StandardCopyOption.ATOMIC_MOVE,
        )
    }

    fun shouldRunAutoCheck(now: Instant = Instant.now()): Boolean {
        val prefs = load()
        if (!prefs.checkUpdates) {
            return false
        }
        if (prefs.lastUpdateCheckAt.isBlank()) {
            return true
        }
        val last = runCatching { OffsetDateTime.parse(prefs.lastUpdateCheckAt).toInstant() }
            .getOrNull() ?: return true
        val elapsedSeconds = now.epochSecond - last.epochSecond
        return elapsedSeconds >= prefs.updateCheckIntervalDays * 86400L
    }

    fun markCheckDone(
        dismissedVersion: String? = null,
        now: Instant = Instant.now(),
    ): AppPrefs {
        val current = load()
        val updated = current.copy(
            lastUpdateCheckAt = DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(
                OffsetDateTime.ofInstant(now, java.time.ZoneOffset.UTC),
            ),
            dismissedUpdateVersion = dismissedVersion ?: current.dismissedUpdateVersion,
        )
        save(updated)
        return updated
    }
}

fun normalizeGithubRepo(value: String): String {
    var text = value.trim()
        .removePrefix("https://github.com/")
        .removePrefix("http://github.com/")
        .trim('/')
    if (text.count { it == '/' } != 1) {
        return DEFAULT_UPDATE_GITHUB_REPO
    }
    val parts = text.split('/', limit = 2)
    val owner = parts[0].trim()
    val name = parts[1].trim().removeSuffix(".git")
    if (owner.isEmpty() || name.isEmpty()) {
        return DEFAULT_UPDATE_GITHUB_REPO
    }
    fun ok(part: String): Boolean =
        part.replace("-", "").replace("_", "").replace(".", "").all { it.isLetterOrDigit() }
    if (!ok(owner) || !ok(name)) {
        return DEFAULT_UPDATE_GITHUB_REPO
    }
    return "$owner/$name"
}

fun AppPrefs.normalized(): AppPrefs {
    val days = updateCheckIntervalDays.coerceIn(
        MIN_UPDATE_CHECK_INTERVAL_DAYS,
        MAX_UPDATE_CHECK_INTERVAL_DAYS,
    )
    return copy(
        updateCheckIntervalDays = days,
        updateGithubRepo = DEFAULT_UPDATE_GITHUB_REPO,
    )
}
