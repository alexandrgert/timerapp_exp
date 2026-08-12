package com.timerapp.linkb24.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.time.Instant
import java.time.format.DateTimeFormatter

const val SETTINGS_BUNDLE_FORMAT = "timerapp-settings"
const val SETTINGS_BUNDLE_VERSION = 1

@Serializable
data class SettingsBundleBitrix(
    @SerialName("webhook_url") val webhookUrl: String = "",
)

data class SettingsImportResult(
    val ok: Boolean,
    val error: String = "",
    val webdav: WebDavConfig? = null,
    val app: AppPrefs? = null,
)

object SettingsBundle {
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun exportJson(webdav: WebDavConfig, app: AppPrefs): String {
        val root = buildJsonObject {
            put("format", SETTINGS_BUNDLE_FORMAT)
            put("version", SETTINGS_BUNDLE_VERSION)
            put(
                "exported_at",
                DateTimeFormatter.ISO_INSTANT.format(Instant.now()),
            )
            put("webdav", json.encodeToJsonElement(WebDavConfig.serializer(), webdav))
            put("app", json.encodeToJsonElement(AppPrefs.serializer(), app.normalized()))
            put(
                "bitrix",
                json.encodeToJsonElement(SettingsBundleBitrix.serializer(), SettingsBundleBitrix()),
            )
            put("ui", buildJsonObject {})
        }
        return json.encodeToString(JsonObject.serializer(), root)
    }

    fun parse(raw: String): SettingsImportResult {
        val root = runCatching { json.parseToJsonElement(raw).jsonObject }
            .getOrElse { return SettingsImportResult(ok = false, error = "Некорректный JSON") }
        val format = root["format"]?.jsonPrimitive?.content.orEmpty()
        if (format != SETTINGS_BUNDLE_FORMAT) {
            return SettingsImportResult(
                ok = false,
                error = "Неизвестный формат файла (ожидается timerapp-settings)",
            )
        }
        val version = root["version"]?.jsonPrimitive?.content?.toIntOrNull() ?: 0
        if (version < 1 || version > SETTINGS_BUNDLE_VERSION) {
            return SettingsImportResult(ok = false, error = "Неподдерживаемая версия файла: $version")
        }
        val webdav = root["webdav"]?.let {
            runCatching { json.decodeFromJsonElement(WebDavConfig.serializer(), it) }.getOrNull()
        }
        val app = root["app"]?.let {
            runCatching { json.decodeFromJsonElement(AppPrefs.serializer(), it) }.getOrNull()?.normalized()
        }
        if (webdav == null && app == null) {
            return SettingsImportResult(ok = false, error = "В файле нет распознанных настроек")
        }
        return SettingsImportResult(ok = true, webdav = webdav, app = app)
    }

    fun mergeImportedWebDav(imported: WebDavConfig, current: WebDavConfig): WebDavConfig {
        return imported.copy(
            deviceId = current.deviceId.ifBlank { imported.deviceId },
            lastSyncAt = current.lastSyncAt,
            lastError = "",
            lastRemoteContentHash = current.lastRemoteContentHash,
            lastSyncHadConflict = false,
            pendingNotice = "",
            pendingRemoteHash = "",
            pendingRemoteRemindAt = null,
        ).withDeviceId()
    }
}
