package com.timerapp.linkb24.ui

import android.app.Application
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.test.platform.app.InstrumentationRegistry
import com.timerapp.linkb24.data.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.nio.file.Files

class SessionFlowTest {
    @get:Rule val compose = createComposeRule()

    @Test fun task_history_manual_save_survives_repository_reload() {
        // The real ViewModel sees only this isolated test directory; no installed app data/config is read.
        val parent = InstrumentationRegistry.getInstrumentation().targetContext.cacheDir
        val directory = Files.createTempDirectory(parent.toPath(), "session-flow-").toFile()
        val application = object : Application() {
            override fun getFilesDir(): File = directory
        }
        val repository = TaskRepository(application)
        WebDavConfigRepository(application).save(WebDavConfig(enabled = false, syncOnStartup = false))
        val initial = repository.createTask("Проверка ручной сессии", AppDataDto())
        repository.save(initial)
        val store = ViewModelStore()
        lateinit var model: TaskViewModel
        try {
            compose.runOnUiThread {
                model = ViewModelProvider(store, object : ViewModelProvider.Factory {
                    @Suppress("UNCHECKED_CAST")
                    override fun <T : ViewModel> create(modelClass: Class<T>): T = TaskViewModel(application) as T
                })[TaskViewModel::class.java]
            }
            compose.setContent { MaterialTheme { TimerAppExperimentApp(model) } }
            compose.waitUntil(timeoutMillis = 10_000) { !model.uiState.value.isLoading }
            compose.onNodeWithContentDescription("История").performScrollTo().performClick()
            compose.onNodeWithText("Добавить запись").performClick()
            fun field(tag: String, value: String) {
                compose.onNodeWithTag(tag).performScrollTo().performTextReplacement(value)
            }
            field("start-date", "2024-02-29")
            field("start-time", "23:30")
            field("end-date", "2024-03-01")
            field("end-time", "00:45")
            field("session-comment", "Сохранённый комментарий")
            compose.onNodeWithTag("session-save").performClick()
            compose.waitUntil(timeoutMillis = 10_000) {
                model.uiState.value.tasks.singleOrNull()?.sessions?.size == 1
            }
            compose.onNodeWithText("История сессий").assertIsDisplayed()
            val reloaded = TaskRepository(File(directory, "data.json")).load()
            val task = reloaded.tasks.single()
            val session = task.sessions.single()
            assertEquals(initial.tasks.single().id, task.id)
            assertEquals(TaskStatus.PAUSED, task.status)
            assertEquals("Сохранённый комментарий", session.comment)
            assertEquals(4500L, taskDurationSeconds(task))
            assertTrue(session.startedAt.startsWith("2024-02-29T23:30:00"))
            assertTrue(session.endedAt!!.startsWith("2024-03-01T00:45:00"))
        } finally {
            compose.runOnUiThread { store.clear() }
            directory.deleteRecursively()
        }
    }
}
