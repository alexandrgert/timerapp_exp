package com.timerapp.linkb24.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import com.timerapp.linkb24.data.SessionDto
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class SessionDialogsTest {
    @get:Rule val compose = createComposeRule()

    private fun field(tag: String, text: String) {
        compose.onNodeWithTag(tag).performScrollTo().performTextReplacement(text)
    }

    @Test fun opening_and_cancelling_add_does_not_save() {
        val open = mutableStateOf(true)
        var calls = 0
        compose.setContent { MaterialTheme {
            if (open.value) SessionEditorDialog(null, false, { open.value = false }) { _, _, _, _ -> calls++ }
            else Text("Закрыто")
        } }
        compose.onNodeWithText("Добавить сессию").assertIsDisplayed()
        compose.runOnIdle { assertEquals(0, calls) }
        compose.onNodeWithText("Отмена").performClick()
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
        compose.runOnIdle { assertEquals(0, calls) }
    }

    @Test fun invalid_range_remains_open_then_valid_arbitrary_interval_saves() {
        val open = mutableStateOf(true)
        var saved: Triple<String, String?, String>? = null
        compose.setContent { MaterialTheme {
            if (open.value) SessionEditorDialog(null, false, { open.value = false }) { start, end, comment, result ->
                saved = Triple(start, end, comment); result(null)
            } else Text("Закрыто")
        } }
        field("start-date", "2024-02-29")
        field("start-time", "23:30")
        field("end-date", "2024-02-29")
        field("end-time", "22:30")
        compose.onNodeWithTag("session-save").performClick()
        compose.runOnIdle { assertNull(saved) }
        compose.onNodeWithText("Добавить сессию").assertIsDisplayed()
        field("end-date", "2024-03-01")
        field("end-time", "00:30")
        field("session-comment", "Ночная работа")
        compose.onNodeWithTag("session-save").performClick()
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
        compose.runOnIdle {
            assertNotNull(saved)
            assertTrue(saved!!.first.startsWith("2024-02-29T23:30:00"))
            assertTrue(saved!!.second!!.startsWith("2024-03-01T00:30:00"))
            assertEquals("Ночная работа", saved!!.third)
        }
    }

    @Test fun persistence_error_keeps_draft_for_retry_and_comment_edit_keeps_precision() {
        val original = SessionDto("s", "2026-08-12T10:00:12.123456789+03:00", "2026-08-12T11:00:34.987654321+03:00", "42", "before")
        val open = mutableStateOf(true)
        var calls = 0
        compose.setContent { MaterialTheme {
            if (open.value) SessionEditorDialog(original, true, { open.value = false }) { start, end, comment, result ->
                assertEquals(original.startedAt, start)
                assertEquals(original.endedAt, end)
                assertEquals("after", comment)
                calls++
                result(if (calls == 1) "Недостаточно места" else null)
            } else Text("Закрыто")
        } }
        field("session-comment", "after")
        compose.onNodeWithTag("session-save").performClick()
        compose.onNodeWithText("Недостаточно места").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("session-comment").performScrollTo().assertTextContains("after")
        compose.onNodeWithTag("session-save").performClick()
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
        compose.runOnIdle { assertEquals(2, calls) }
    }

    @Test fun delete_requires_confirmation_and_cancel_does_not_delete() {
        val open = mutableStateOf(true)
        var deleted = 0
        compose.setContent { MaterialTheme {
            if (open.value) DeleteRecordDialog("Удалить сессию?", "Период сессии", false, false,
                { open.value = false }, { result -> deleted++; result(null) })
            else Text("Закрыто")
        } }
        compose.runOnIdle { assertEquals(0, deleted) }
        compose.onNodeWithText("Отмена").performClick()
        compose.runOnIdle { assertEquals(0, deleted); open.value = true }
        compose.onNodeWithTag("delete-confirm").performClick()
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
        compose.runOnIdle { assertEquals(1, deleted) }
    }

    @Test fun delete_error_can_be_retried() {
        val open = mutableStateOf(true)
        var calls = 0
        compose.setContent { MaterialTheme {
            if (open.value) DeleteRecordDialog("Удалить задачу?", "Задача и история", false, false,
                { open.value = false }, { result -> calls++; result(if (calls == 1) "Ошибка сохранения" else null) })
            else Text("Закрыто")
        } }
        compose.onNodeWithTag("delete-confirm").performClick()
        compose.onNodeWithText("Ошибка сохранения").assertIsDisplayed()
        compose.onNodeWithTag("delete-confirm").performClick()
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
        compose.runOnIdle { assertEquals(2, calls) }
    }

    @Test fun back_cancels_without_saving() {
        val open = mutableStateOf(true)
        var saved = false
        compose.setContent { MaterialTheme {
            if (open.value) SessionEditorDialog(null, false, { open.value = false }) { _, _, _, _ -> saved = true }
            else Text("Закрыто")
        } }
        compose.onNodeWithText("Добавить сессию").assertIsDisplayed()
        androidx.test.espresso.Espresso.pressBack()
        compose.onNodeWithText("Закрыто").assertIsDisplayed()
        compose.runOnIdle { assertFalse(saved) }
    }
}
