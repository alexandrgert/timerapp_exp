package com.timerapp.linkb24.voice

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream
import kotlin.coroutines.coroutineContext

object RussianVoiceModel {
    const val NAME = "sherpa-onnx-zipformer-ru-int8-2025-04-20"
    const val URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$NAME.tar.bz2"
    const val SHA256 = "d6a651569aacc9a177259fa54705dd76acae23f6a4d62ea6797bd220d4b57163"
    const val ARCHIVE_BYTES = 60_239_942L
    const val INSTALLED_BYTES = 74_004_174L
    const val REQUIRED_FREE_BYTES = ARCHIVE_BYTES + INSTALLED_BYTES + 16L * 1024 * 1024
    val REQUIRED_FILES = listOf("encoder.int8.onnx", "decoder.onnx", "joiner.int8.onnx", "tokens.txt")
}

/** Only downloads the pinned public model; audio is never an input to this class. */
class VoiceModelStore(private val root: File) {
    private val modelDir = File(root, RussianVoiceModel.NAME)
    private val cachedArchive = File(root, ".verified-${RussianVoiceModel.SHA256}.tar.bz2")
    @Volatile private var activeCall: Call? = null
    private val client = OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS).followRedirects(true).followSslRedirects(false).build()

    fun readyDirectory(): File? = modelDir.takeIf {
        File(it, ".ready").let { marker -> marker.isFile && marker.readText() == RussianVoiceModel.SHA256 } &&
            RussianVoiceModel.REQUIRED_FILES.all { name -> File(it, name).let { file -> file.isFile && file.length() > 0 } }
    }

    fun hasCachedArchive(): Boolean = cachedArchive.isFile && cachedArchive.length() == RussianVoiceModel.ARCHIVE_BYTES

    fun cancelDownload() { activeCall?.cancel() }

    suspend fun install(onProgress: (downloaded: Long, total: Long, unpacking: Boolean) -> Unit): File =
        installMutex.withLock {
            withContext(Dispatchers.IO) {
                readyDirectory()?.let { return@withContext it }
                require(root.isDirectory || root.mkdirs()) { "Не удалось создать папку голосовой модели." }
                root.listFiles()?.filter {
                    it.name.startsWith(".download-") || it.name.startsWith(".old-") ||
                        (it.name.startsWith(".verified-") && it != cachedArchive)
                }?.forEach { it.deleteRecursively() }
                val installContext = coroutineContext
                val reusable = verifiedArchive(cachedArchive, RussianVoiceModel.ARCHIVE_BYTES, RussianVoiceModel.SHA256) { installContext.ensureActive() }
                val requiredSpace = RussianVoiceModel.REQUIRED_FREE_BYTES - if (reusable) RussianVoiceModel.ARCHIVE_BYTES else 0L
                if (root.usableSpace < requiredSpace) {
                    throw IOException("Для установки нужно ещё ${(requiredSpace + 999_999) / 1_000_000} МБ свободного места. Освободите место и повторите.")
                }
                val staging = File(root, ".download-${UUID.randomUUID()}")
                check(staging.mkdir()) { "Не удалось создать временную папку модели." }
                try {
                    val archive = File(staging, "model.tar.bz2")
                    if (!reusable) {
                        val call = client.newCall(Request.Builder().url(RussianVoiceModel.URL).build())
                        activeCall = call
                        coroutineContext.ensureActive()
                        val digest = MessageDigest.getInstance("SHA-256")
                        call.execute().use { response ->
                            if (!response.isSuccessful) throw IOException("Сервер модели ответил HTTP ${response.code}. Повторите загрузку позже.")
                            val body = response.body ?: throw IOException("Сервер не вернул модель.")
                            val length = body.contentLength()
                            if (length > RussianVoiceModel.ARCHIVE_BYTES) throw IOException("Неожиданный размер модели.")
                            body.byteStream().use { input -> FileOutputStream(archive).use { output ->
                                val buffer = ByteArray(64 * 1024)
                                var copied = 0L
                                var lastPercent = -1L
                                while (true) {
                                    coroutineContext.ensureActive()
                                    val count = input.read(buffer)
                                    if (count < 0) break
                                    copied += count
                                    if (copied > RussianVoiceModel.ARCHIVE_BYTES) throw IOException("Архив модели превышает разрешённый размер.")
                                    output.write(buffer, 0, count)
                                    digest.update(buffer, 0, count)
                                    val percent = copied * 100 / RussianVoiceModel.ARCHIVE_BYTES
                                    if (percent != lastPercent) { onProgress(copied, RussianVoiceModel.ARCHIVE_BYTES, false); lastPercent = percent }
                                }
                                output.fd.sync()
                                if (copied != RussianVoiceModel.ARCHIVE_BYTES) throw IOException("Модель загружена не полностью. Повторите загрузку.")
                            } }
                        }
                        coroutineContext.ensureActive()
                        val checksum = digest.digest().joinToString("") { "%02x".format(it) }
                        if (checksum != RussianVoiceModel.SHA256) throw IOException("Контрольная сумма модели не совпала. Повторите загрузку.")
                        Files.move(archive.toPath(), cachedArchive.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
                    }
                    activeCall = null
                    onProgress(0, RussianVoiceModel.INSTALLED_BYTES, true)
                    cachedArchive.inputStream().use { input ->
                        extractModelArchive(input, staging, RussianVoiceModel.NAME, RussianVoiceModel.INSTALLED_BYTES, 64,
                            onProgress = { bytes -> onProgress(bytes, RussianVoiceModel.INSTALLED_BYTES, true) },
                            checkCancelled = { installContext.ensureActive() })
                    }
                    val extracted = File(staging, RussianVoiceModel.NAME)
                    if (!RussianVoiceModel.REQUIRED_FILES.all { File(extracted, it).let { f -> f.isFile && f.length() > 0 } }) {
                        throw IOException("В архиве не хватает файлов модели.")
                    }
                    FileOutputStream(File(extracted, ".ready")).use {
                        it.write(RussianVoiceModel.SHA256.toByteArray()); it.fd.sync()
                    }
                    coroutineContext.ensureActive()
                    // Existing incomplete installation is moved aside only after the replacement is complete.
                    val previous = File(root, ".old-${UUID.randomUUID()}")
                    if (modelDir.exists()) Files.move(modelDir.toPath(), previous.toPath(), StandardCopyOption.ATOMIC_MOVE)
                    try {
                        Files.move(extracted.toPath(), modelDir.toPath(), StandardCopyOption.ATOMIC_MOVE)
                    } catch (error: Exception) {
                        if (previous.exists() && !modelDir.exists()) Files.move(previous.toPath(), modelDir.toPath(), StandardCopyOption.ATOMIC_MOVE)
                        throw error
                    }
                    previous.deleteRecursively()
                    cachedArchive.delete()
                    // Remove only the obsolete, app-owned Vosk model after the replacement is ready.
                    File(root, "vosk-model-small-ru-0.22").deleteRecursively()
                    modelDir
                } finally {
                    activeCall = null
                    staging.deleteRecursively()
                }
            }
        }

    companion object { private val installMutex = Mutex() }
}

/** Size/path limits apply to actual streamed bytes, not untrusted TAR metadata. */
internal fun extractModelArchive(
    source: InputStream, destination: File, expectedRoot: String,
    maxBytes: Long, maxEntries: Int, onProgress: (Long) -> Unit = {}, checkCancelled: () -> Unit = {},
) {
    var total = 0L
    var count = 0
    val seen = mutableSetOf<String>()
    val safeRoot = destination.canonicalFile
    // Bzip2 reads compressed bits through single-byte reads: buffer BEFORE decompression.
    TarArchiveInputStream(BZip2CompressorInputStream(source.buffered(64 * 1024))).use { tar ->
        while (true) {
            checkCancelled()
            val entry = tar.nextTarEntry ?: break
            if (!entry.isDirectory && !entry.isFile || entry.isSymbolicLink || entry.isLink || entry.isSparse)
                throw IOException("Недопустимый тип записи в архиве модели.")
            count++
            if (count > maxEntries) throw IOException("Слишком много файлов в модели.")
            val name = entry.name
            val segments = name.split('/')
            if (name.startsWith('/') || name.contains('\\') || segments.any { it == ".." || it == "." } ||
                segments.firstOrNull() != expectedRoot || !seen.add(name)) throw IOException("Недопустимый путь в архиве модели.")
            val output = File(destination, name).canonicalFile
            if (!output.toPath().startsWith(safeRoot.toPath()) || output == safeRoot) throw IOException("Путь вне папки модели.")
            if (entry.isDirectory) {
                if (!output.isDirectory && !output.mkdirs()) throw IOException("Не удалось создать папку модели.")
            } else {
                if (!output.parentFile.isDirectory && !output.parentFile.mkdirs()) throw IOException("Не удалось создать папку модели.")
                FileOutputStream(output).use { file ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        checkCancelled()
                        val size = tar.read(buffer)
                        if (size < 0) break
                        total += size
                        if (total > maxBytes) throw IOException("Распакованная модель слишком велика.")
                        file.write(buffer, 0, size)
                        onProgress(total)
                    }
                    file.fd.sync()
                }
            }

        }
    }
    if (count == 0 || total == 0L) throw IOException("Архив модели пуст.")
}

/** A completed download is reused only after exact byte count and SHA verification on every retry. */
internal fun verifiedArchive(file: File, expectedBytes: Long, expectedSha: String, checkCancelled: () -> Unit = {}): Boolean {
    if (!file.isFile) return false
    if (file.length() != expectedBytes) { file.delete(); return false }
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().buffered(64 * 1024).use { input ->
        val buffer = ByteArray(64 * 1024)
        while (true) {
            checkCancelled()
            val count = input.read(buffer)
            if (count < 0) break
            digest.update(buffer, 0, count)
        }
    }
    val valid = digest.digest().joinToString("") { "%02x".format(it) } == expectedSha
    if (!valid) file.delete()
    return valid
}
