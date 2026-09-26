package com.timerapp.linkb24.voice

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

internal data class VoiceInputState(
    val checking: Boolean = true,
    val modelReady: Boolean = false,
    val downloading: Boolean = false,
    val archiveCached: Boolean = false,
    val downloadedBytes: Long = 0,
    val unpacking: Boolean = false,
    val loading: Boolean = false,
    val recording: Boolean = false,
    val stopping: Boolean = false,
    val processing: Boolean = false,
    val text: String = "",
    val partial: String = "",
    val error: String? = null,
) {
    val microphoneBusy: Boolean get() = loading || recording || stopping || processing
}

internal class VoiceInputController(context: Context) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val store = VoiceModelStore(File(context.filesDir, "voice-model"))
    private val _state = MutableStateFlow(VoiceInputState())
    val state = _state.asStateFlow()
    private var operation: Job? = null
    private val stopRequested = AtomicBoolean(false)

    init {
        operation = scope.launch {
            try {
                val (ready, cached) = withContext(Dispatchers.IO) { (store.readyDirectory() != null) to store.hasCachedArchive() }
                _state.update { it.copy(checking = false, modelReady = ready, archiveCached = cached) }
            } catch (error: Exception) {
                _state.update { it.copy(checking = false, error = voiceFailureMessage(error)) }
            }
        }
    }

    fun download() {
        if (_state.value.checking || _state.value.downloading || _state.value.microphoneBusy) return
        _state.update { it.copy(downloading = true, downloadedBytes = 0, unpacking = false, error = null) }
        operation = scope.launch {
            try {
                store.install { bytes, _, unpacking ->
                    _state.update { it.copy(downloadedBytes = bytes, unpacking = unpacking) }
                }
                _state.update { it.copy(downloading = false, modelReady = true, unpacking = false) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                if (error !is Exception && error !is LinkageError && error !is OutOfMemoryError) throw error
                _state.update { it.copy(error = modelInstallFailureMessage(error)) }
            } finally {
                _state.update { it.copy(downloading = false, unpacking = false, archiveCached = store.hasCachedArchive()) }
            }
        }
    }

    fun cancelDownload() {
        store.cancelDownload()
        operation?.cancel()
    }

    fun start() {
        if (!_state.value.modelReady || _state.value.microphoneBusy || _state.value.downloading) return
        val before = _state.value.text
        stopRequested.set(false)
        _state.update { it.copy(loading = true, partial = "", error = null) }
        operation = scope.launch {
            try {
                val directory = withContext(Dispatchers.IO) { store.readyDirectory() }
                    ?: throw IllegalStateException("Модель недоступна. Закройте диктовку и загрузите её заново.")
                val finalText = OfflineDictation().listen(directory, stopRequested::get,
                    onReady = { _state.update { it.copy(loading = false, recording = true) } },
                    onProcessing = { _state.update { it.copy(loading = false, recording = false, stopping = false, processing = true) } })
                _state.update { it.copy(text = appendDictation(before, finalText), partial = "",
                    error = if (finalText.isBlank()) "Речь не распознана. Проверьте микрофон и повторите диктовку." else null) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                if (error !is Exception && error !is LinkageError && error !is OutOfMemoryError) throw error
                _state.update { it.copy(text = appendDictation(it.text, it.partial), partial = "", error = voiceFailureMessage(error)) }
            } finally {
                _state.update { it.copy(loading = false, recording = false, stopping = false, processing = false) }
            }
        }
    }

    fun stop() {
        if (!_state.value.microphoneBusy || _state.value.processing) return
        stopRequested.set(true)
        _state.update { it.copy(stopping = true) }
    }

    fun editText(text: String) {
        if (!_state.value.microphoneBusy) _state.update { it.copy(text = text) }
    }

    fun permissionDenied() {
        _state.update { it.copy(error = "Нет доступа к микрофону. Разрешите его в настройках приложения или продолжите вводить текст вручную.") }
    }

    fun close() {
        stopRequested.set(true)
        store.cancelDownload()
        scope.cancel()
    }
}

internal fun voiceFailureMessage(error: Throwable): String = when {
    error is SecurityException -> "Нет доступа к микрофону. Проверьте разрешение в настройках приложения."
    error is OutOfMemoryError -> "Недостаточно оперативной памяти для распознавания. Закройте другие приложения и повторите."
    error is LinkageError -> "Голосовой движок не удалось загрузить на этом устройстве. Ручной ввод доступен."
    generateSequence(error) { it.cause }.any { it.message.orEmpty().contains("ENOSPC", true) || it.message.orEmpty().contains("No space", true) || it.message.orEmpty().contains("quota", true) } ->
        "Недостаточно места для модели. Освободите место и повторите загрузку."
    else -> "Не удалось выполнить диктовку: ${error.message ?: "проверьте подключение при загрузке модели и повторите"}"
}

internal fun modelInstallFailureMessage(error: Throwable): String = when {
    error is OutOfMemoryError -> "Недостаточно оперативной памяти для распаковки модели. Закройте другие приложения и повторите установку."
    error is LinkageError -> "Компонент распаковки модели недоступен на этом устройстве. Нужна исправленная версия приложения."
    error is SecurityException -> "Не удалось записать модель в папку приложения. Повторите установку."
    generateSequence(error) { it.cause }.any { it.message.orEmpty().contains("ENOSPC", true) || it.message.orEmpty().contains("No space", true) || it.message.orEmpty().contains("quota", true) } ->
        "Недостаточно места для модели. Освободите место и повторите установку."
    else -> "Не удалось установить модель: ${error.message ?: error.javaClass.simpleName}. Повторите установку."
}
