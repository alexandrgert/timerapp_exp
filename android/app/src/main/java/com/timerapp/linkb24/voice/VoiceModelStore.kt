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
import java.util.zip.ZipInputStream
import kotlin.coroutines.coroutineContext

object RussianVoiceModel {
    const val NAME = "vosk-model-small-ru-0.22"
    const val URL = "https://alphacephei.com/vosk/models/$NAME.zip"
    const val SHA256 = "961d5ff98a17f4aa6de69864d0aa71fa5bac682301d2b5d17a3f24c5c99a46d4"
    const val ARCHIVE_BYTES = 46_236_750L
    const val INSTALLED_BYTES = 91_289_240L
    const val REQUIRED_FREE_BYTES = ARCHIVE_BYTES + INSTALLED_BYTES + 16L * 1024 * 1024
    val REQUIRED_FILES = listOf("am/final.mdl", "conf/model.conf", "conf/mfcc.conf", "graph/Gr.fst", "graph/HCLr.fst",
        "graph/disambig_tid.int", "graph/phones/word_boundary.int", "ivector/final.dubm", "ivector/final.ie",
        "ivector/final.mat", "ivector/global_cmvn.stats", "ivector/online_cmvn.conf", "ivector/splice.conf")
}

/** Only downloads the pinned public model; audio is never an input to this class. */
class VoiceModelStore(private val root: File) {
    private val modelDir = File(root, RussianVoiceModel.NAME)
    @Volatile private var activeCall: Call? = null
    private val client = OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false).build()

    fun readyDirectory(): File? = modelDir.takeIf {
        File(it, ".ready").let { marker -> marker.isFile && marker.readText() == RussianVoiceModel.SHA256 } &&
            RussianVoiceModel.REQUIRED_FILES.all { name -> File(it, name).let { file -> file.isFile && file.length() > 0 } }
    }

    fun cancelDownload() { activeCall?.cancel() }

    suspend fun install(onProgress: (downloaded: Long, total: Long, unpacking: Boolean) -> Unit): File =
        installMutex.withLock {
            withContext(Dispatchers.IO) {
                readyDirectory()?.let { return@withContext it }
                require(root.isDirectory || root.mkdirs()) { "Не удалось создать папку голосовой модели." }
                root.listFiles()?.filter { it.name.startsWith(".download-") || it.name.startsWith(".old-") }?.forEach { it.deleteRecursively() }
                if (root.usableSpace < RussianVoiceModel.REQUIRED_FREE_BYTES) {
                    throw IOException("Для загрузки и распаковки нужно не менее 155 МБ свободного места. Освободите место и повторите.")
                }
                val staging = File(root, ".download-${UUID.randomUUID()}")
                check(staging.mkdir()) { "Не удалось создать временную папку модели." }
                try {
                    val archive = File(staging, "model.zip")
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
                    onProgress(RussianVoiceModel.ARCHIVE_BYTES, RussianVoiceModel.ARCHIVE_BYTES, true)
                    val installContext = coroutineContext
                    archive.inputStream().use { input ->
                        extractModelArchive(input, staging, RussianVoiceModel.NAME, RussianVoiceModel.INSTALLED_BYTES, 64) {
                            installContext.ensureActive()
                        }
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
                    modelDir
                } finally {
                    activeCall = null
                    staging.deleteRecursively()
                }
            }
        }

    companion object { private val installMutex = Mutex() }
}

/** Size/path limits apply to actual streamed bytes, not untrusted ZIP metadata. */
internal fun extractModelArchive(
    source: InputStream, destination: File, expectedRoot: String,
    maxBytes: Long, maxEntries: Int, checkCancelled: () -> Unit = {},
) {
    var total = 0L
    var count = 0
    val seen = mutableSetOf<String>()
    val safeRoot = destination.canonicalFile
    ZipInputStream(source).use { zip ->
        while (true) {
            checkCancelled()
            val entry = zip.nextEntry ?: break
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
                        val size = zip.read(buffer)
                        if (size < 0) break
                        total += size
                        if (total > maxBytes) throw IOException("Распакованная модель слишком велика.")
                        file.write(buffer, 0, size)
                    }
                    file.fd.sync()
                }
            }
            zip.closeEntry()
        }
    }
    if (count == 0 || total == 0L) throw IOException("Архив модели пуст.")
}
