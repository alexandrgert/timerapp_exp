package com.timerapp.linkb24.voice

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineTransducerModelConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import kotlin.coroutines.coroutineContext

internal fun appendDictation(existing: String, recognized: String): String {
    val addition = recognized.trim()
    if (addition.isEmpty()) return existing
    return if (existing.isBlank()) addition else existing + (if (existing.last().isWhitespace()) "" else " ") + addition
}

/** One complete utterance, bounded to 60 seconds, is decoded after the microphone closes.
 * No mid-word chunking, concurrent decode/capture gaps, audio files or network recognition.
 */
internal class OfflineDictation {
    @SuppressLint("MissingPermission") // Caller obtains RECORD_AUDIO before start; revocation becomes an error.
    suspend fun listen(
        modelDirectory: File,
        shouldStop: () -> Boolean,
        onReady: () -> Unit,
        onProcessing: () -> Unit,
    ): String = recognizerMutex.withLock {
        withContext(Dispatchers.IO) {
            coroutineContext.ensureActive()
            if (shouldStop()) return@withContext ""
            val recognizer = OfflineRecognizer(config = OfflineRecognizerConfig(
                modelConfig = OfflineModelConfig(
                    transducer = OfflineTransducerModelConfig(
                        encoder = File(modelDirectory, "encoder.int8.onnx").absolutePath,
                        decoder = File(modelDirectory, "decoder.onnx").absolutePath,
                        joiner = File(modelDirectory, "joiner.int8.onnx").absolutePath,
                    ),
                    tokens = File(modelDirectory, "tokens.txt").absolutePath,
                    modelType = "transducer",
                    numThreads = 2,
                    provider = "cpu",
                ),
            ))
            try {
                coroutineContext.ensureActive()
                if (shouldStop()) return@withContext ""
                val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
                if (minBuffer <= 0) throw IOException("Устройство не поддерживает запись голоса 16 кГц.")
                val audio = BoundedPcmBuffer(SAMPLE_RATE * MAX_RECORDING_SECONDS)
                val recorder = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuffer, SAMPLE_RATE))
                try {
                    if (recorder.state != AudioRecord.STATE_INITIALIZED) throw IOException("Микрофон недоступен или занят другим приложением.")
                    coroutineContext.ensureActive()
                    if (shouldStop()) return@withContext ""
                    recorder.startRecording()
                    if (recorder.recordingState != AudioRecord.RECORDSTATE_RECORDING) throw IOException("Не удалось начать запись микрофона.")
                    onReady()
                    val samples = ShortArray(SAMPLE_RATE / 5)
                    while (!shouldStop() && !audio.full) {
                        coroutineContext.ensureActive()
                        val size = recorder.read(samples, 0, minOf(samples.size, audio.remaining))
                        if (size < 0) throw IOException("Микрофон перестал передавать звук. Проверьте доступ и повторите.")
                        if (size == 0) continue
                        audio.append(samples, size)
                    }
                } finally {
                    if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) runCatching { recorder.stop() }
                    recorder.release()
                }
                coroutineContext.ensureActive()
                if (audio.size == 0) return@withContext ""
                onProcessing()
                val stream = recognizer.createStream()
                try {
                    stream.acceptWaveform(audio.normalizedSamples(), SAMPLE_RATE)
                    coroutineContext.ensureActive()
                    recognizer.decode(stream)
                    coroutineContext.ensureActive()
                    recognizer.getResult(stream).text.trim()
                } finally {
                    stream.release()
                }
            } finally {
                recognizer.release()
            }
        }
    }

    companion object {
        // Closing a dialog cancels its coroutine but JNI finishes before resources can release.
        // A newly opened dialog waits cancellably instead of loading a second native model/mic.
        private val recognizerMutex = Mutex()
        private const val SAMPLE_RATE = 16_000
        const val MAX_RECORDING_SECONDS = 60
    }
}

/** Maximum PCM allocation is fixed; native inference sees only actual captured samples. */
internal class BoundedPcmBuffer(capacity: Int) {
    private val data = ShortArray(capacity)
    var size: Int = 0
        private set
    val remaining: Int get() = data.size - size
    val full: Boolean get() = remaining == 0

    fun append(samples: ShortArray, count: Int) {
        require(count in 0..samples.size && count <= remaining)
        samples.copyInto(data, size, 0, count)
        size += count
    }

    fun normalizedSamples(): FloatArray = FloatArray(size) { data[it] / 32768f }
}
