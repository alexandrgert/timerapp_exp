package com.timerapp.linkb24.voice

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.timerapp.linkb24.data.AppJson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File
import java.io.IOException
import kotlin.coroutines.coroutineContext

internal fun appendDictation(existing: String, recognized: String): String {
    val addition = recognized.trim()
    if (addition.isEmpty()) return existing
    return if (existing.isBlank()) addition else existing + (if (existing.last().isWhitespace()) "" else " ") + addition
}

internal fun recognizedText(payload: String, partial: Boolean = false): String = runCatching {
    AppJson.parseToJsonElement(payload).jsonObject[if (partial) "partial" else "text"]?.jsonPrimitive?.content.orEmpty()
}.getOrDefault("")

/** Microphone samples stay in RAM and are passed only to the local native recognizer. */
internal class OfflineDictation {
    @SuppressLint("MissingPermission") // Caller obtains RECORD_AUDIO immediately before start; revocation is handled as an error.
    suspend fun listen(
        modelDirectory: File,
        shouldStop: () -> Boolean,
        onReady: () -> Unit,
        onText: (String, String) -> Unit,
    ): String = withContext(Dispatchers.IO) {
        var committed = ""
        Model(modelDirectory.absolutePath).use { model ->
            coroutineContext.ensureActive()
            if (shouldStop()) return@withContext committed
            Recognizer(model, SAMPLE_RATE.toFloat()).use { recognizer ->
                val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
                if (minBuffer <= 0) throw IOException("Устройство не поддерживает запись голоса 16 кГц.")
                val recorder = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuffer, SAMPLE_RATE))
                try {
                    if (recorder.state != AudioRecord.STATE_INITIALIZED) throw IOException("Микрофон недоступен или занят другим приложением.")
                    coroutineContext.ensureActive()
                    if (shouldStop()) return@withContext committed
                    recorder.startRecording()
                    if (recorder.recordingState != AudioRecord.RECORDSTATE_RECORDING) throw IOException("Не удалось начать запись микрофона.")
                    onReady()
                    val samples = ShortArray(SAMPLE_RATE / 5)
                    while (!shouldStop()) {
                        coroutineContext.ensureActive()
                        val size = recorder.read(samples, 0, samples.size)
                        if (size < 0) throw IOException("Микрофон перестал передавать звук. Проверьте доступ и повторите.")
                        if (size == 0) continue
                        if (recognizer.acceptWaveForm(samples, size)) {
                            committed = appendDictation(committed, recognizedText(recognizer.result))
                            onText(committed, "")
                        } else {
                            onText(committed, recognizedText(recognizer.partialResult, partial = true))
                        }
                    }
                    committed = appendDictation(committed, recognizedText(recognizer.finalResult))
                    onText(committed, "")
                    committed
                } finally {
                    if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) runCatching { recorder.stop() }
                    recorder.release()
                }
            }
        }
    }

    companion object { private const val SAMPLE_RATE = 16_000 }
}
