package com.timerapp.linkb24.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import com.timerapp.linkb24.data.TaskDto
import com.timerapp.linkb24.voice.VoiceInputButton
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class VoiceEntryTest {
    @get:Rule val compose = createComposeRule()

    @Test fun cancelling_voice_preserves_original_field_without_microphone_or_download() {
        val text = mutableStateOf("Уже введённое описание")
        compose.setContent { MaterialTheme {
            OutlinedTextField(value = text.value, onValueChange = { text.value = it }, modifier = Modifier.testTag("description"),
                trailingIcon = { VoiceInputButton("описание", text.value) { text.value = it } })
        } }
        compose.onNodeWithContentDescription("Голосом: описание").performClick()
        compose.onNodeWithText("Диктовка офлайн").assertExists()
        compose.onNodeWithText("Отмена").performClick()
        compose.onNodeWithTag("description").assertTextContains("Уже введённое описание")
        compose.runOnIdle { assertEquals("Уже введённое описание", text.value) }
    }

    @Test fun creation_saves_description_and_keeps_both_fields_on_failure() {
        val open = mutableStateOf(true)
        var attempts = 0
        compose.setContent { MaterialTheme {
            if (open.value) CreateTaskDialog({ open.value = false }) { title, description, result ->
                assertEquals("Задача", title)
                assertEquals("Описание работы", description)
                attempts++
                result(if (attempts == 1) "Недостаточно места" else null)
            } else Text("Закрыто")
        } }
        compose.onNodeWithContentDescription("Голосом: название задачи").assertExists()
        compose.onNodeWithContentDescription("Голосом: описание задачи").assertExists()
        compose.onNodeWithTag("create-title").performScrollTo().performTextReplacement("Задача")
        compose.onNodeWithTag("create-description").performScrollTo().performTextReplacement("Описание работы")
        compose.onNodeWithText("Создать").performClick()
        compose.onNodeWithText("Недостаточно места").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("create-description").performScrollTo().assertTextContains("Описание работы")
        compose.onNodeWithText("Создать").performClick()
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
        compose.runOnIdle { assertEquals(2, attempts) }
    }

    @Test fun editing_waits_for_persistence_and_keeps_dictated_description_for_retry() {
        val open = mutableStateOf(true)
        var attempts = 0
        var finishSave: ((String?) -> Unit)? = null
        val draft = "Исходное описание добавлено голосом"
        compose.setContent { MaterialTheme {
            if (open.value) EditTaskDialog(
                task = TaskDto("t", "2026-09-26", "Задача", description = "Исходное описание"),
                onDismiss = { open.value = false },
                onConfirm = { title, description, _, _, result ->
                    assertEquals("Задача", title)
                    assertEquals(draft, description)
                    attempts++
                    finishSave = result
                },
            ) else Text("Закрыто")
        } }
        compose.onNodeWithTag("edit-description").performScrollTo().performTextReplacement(draft)
        compose.onNodeWithTag("edit-save").performClick()
        compose.onNodeWithTag("edit-save").assertIsNotEnabled()
        compose.onNodeWithText("Отмена").assertIsNotEnabled()
        compose.onNodeWithTag("edit-description").assertIsNotEnabled()
        compose.runOnIdle { assertTrue(open.value); assertEquals(1, attempts); finishSave!!("Недостаточно места") }
        compose.onNodeWithText("Недостаточно места").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("edit-description").performScrollTo().assertTextContains(draft)
        compose.onNodeWithTag("edit-save").assertIsEnabled().performClick()
        compose.runOnIdle { assertTrue(open.value); assertEquals(2, attempts); finishSave!!(null) }
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
    }
}
