package com.timerapp.linkb24.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

enum class TaskStatus {
    @SerialName("open")
    OPEN,

    @SerialName("running")
    RUNNING,

    @SerialName("paused")
    PAUSED,

    @SerialName("completed")
    COMPLETED,
}

@Serializable
data class SessionDto(
    val id: String,
    @SerialName("started_at") val startedAt: String,
    @SerialName("ended_at") val endedAt: String? = null,
    @SerialName("bitrix_record_id") val bitrixRecordId: String? = null,
    val comment: String = "",
)

@Serializable
data class BitrixLinkDto(
    val source: String,
    val id: String,
)

@Serializable
data class TaskDto(
    val id: String,
    val day: String,
    val title: String,
    val description: String = "",
    val result: String = "",
    val status: TaskStatus = TaskStatus.OPEN,
    val sessions: List<SessionDto> = emptyList(),
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("completed_at") val completedAt: String? = null,
    @SerialName("continuation_of") val continuationOf: String? = null,
    val bitrix: BitrixLinkDto? = null,
    @SerialName("planned_days") val plannedDays: List<String> = emptyList(),
    @SerialName("daily_priorities") val dailyPriorities: Map<String, Int> = emptyMap(),
    @SerialName("keep_priority") val keepPriority: Boolean = false,
)

@Serializable
data class FocusTimerDto(
    @SerialName("selected_minutes") val selectedMinutes: Int = 25,
    @SerialName("duration_minutes") val durationMinutes: Int? = null,
    @SerialName("ends_at") val endsAt: String? = null,
    @SerialName("session_task_id") val sessionTaskId: String? = null,
    @SerialName("paused_task_id") val pausedTaskId: String? = null,
)

@Serializable
data class UiSettingsDto(
    @SerialName("schema_version") val schemaVersion: Int = 2,
    @SerialName("plan_rollover_day") val planRolloverDay: String = "",
    @SerialName("filter_open_only") val filterOpenOnly: Boolean = false,
    @SerialName("reminder_interval_minutes") val reminderIntervalMinutes: Int = 15,
    @SerialName("focus_timer") val focusTimer: FocusTimerDto = FocusTimerDto(),
    @SerialName("priority_filter") val priorityFilter: List<Int> = listOf(1, 2, 3, 4),
)

@Serializable
data class AppDataDto(
    val tasks: List<TaskDto> = emptyList(),
    val ui: UiSettingsDto = UiSettingsDto(),
)

val AppJson = Json {
    ignoreUnknownKeys = true
    encodeDefaults = true
    explicitNulls = false
    prettyPrint = true
}
