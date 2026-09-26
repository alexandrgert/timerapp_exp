package com.timerapp.linkb24.ui

import android.Manifest
import android.os.Build
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Before
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import com.timerapp.linkb24.data.FocusTimerDto
import com.timerapp.linkb24.data.TaskDto
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.time.Instant

class FocusControlsTest {
    @get:Rule val compose = createComposeRule()

    @Before fun grantNotificationPermissionForFormTests() {
        if (Build.VERSION.SDK_INT >= 33) {
            val instrumentation = InstrumentationRegistry.getInstrumentation()
            instrumentation.uiAutomation.grantRuntimePermission(
                instrumentation.targetContext.packageName, Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    @Test fun invalidDurationDoesNotStartAndErrorFromSaveKeepsForm() {
        var calls = 0
        compose.setContent { MaterialTheme {
            FocusStartDialog(TaskDto("task", "2026-09-26", "Работа"), 25, false, {}) { _, _, result ->
                calls++; result("Не удалось сохранить")
            }
        } }
        compose.onNodeWithText("Минуты (1–180)").performTextReplacement("0")
        compose.onNodeWithText("Начать").performClick()
        compose.runOnIdle { assertEquals(0, calls) }
        compose.onNodeWithText("Укажите от 1 до 180 минут.").assertExists()
        compose.onNodeWithText("Минуты (1–180)").performScrollTo().performTextReplacement("10")
        compose.onNodeWithText("Начать").performClick()
        compose.onNodeWithText("Не удалось сохранить").assertExists()
        compose.runOnIdle { assertEquals(1, calls) }
    }

    @Test fun activeCountdownProvidesVisibleStop() {
        var stopped = false
        val now = Instant.parse("2026-09-26T10:00:00Z")
        compose.setContent { MaterialTheme {
            ActiveFocusPanel(FocusTimerDto(endsAt = now.plusSeconds(90).toString()), "Работа", now.toEpochMilli()) { stopped = true }
        } }
        compose.onNodeWithText("01:30").assertIsDisplayed()
        compose.onNodeWithText("Остановить концентрацию").performClick()
        compose.runOnIdle { assertTrue(stopped) }
    }
}
