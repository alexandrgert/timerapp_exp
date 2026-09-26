package com.timerapp.linkb24.voice

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorOutputStream
import kotlin.io.path.createTempDirectory

class VoiceInputTest {
    @Test fun dictation_appends_without_erasing_existing_text_or_newline() {
        assertEquals("старое новый текст", appendDictation("старое", " новый текст "))
        assertEquals("старое\nновый текст", appendDictation("старое\n", "новый текст"))
        assertEquals("  старое  ", appendDictation("  старое  ", " "))
        assertEquals("новый текст", appendDictation("", "новый текст"))
    }

    @Test fun pcm_buffer_preserves_order_and_normalizes_signed_samples() {
        val buffer = BoundedPcmBuffer(4)
        buffer.append(shortArrayOf(Short.MIN_VALUE, 0), 2)
        buffer.append(shortArrayOf(Short.MAX_VALUE, 16384), 2)
        assertTrue(buffer.full)
        assertEquals(0, buffer.remaining)
        assertArrayEquals(floatArrayOf(-1f, 0f, 32767f / 32768f, .5f), buffer.normalizedSamples(), 0f)
    }

    @Test fun pcm_buffer_has_no_padding_and_rejects_overflow() {
        val buffer = BoundedPcmBuffer(2)
        buffer.append(shortArrayOf(123), 1)
        assertEquals(1, buffer.normalizedSamples().size)
        try {
            buffer.append(shortArrayOf(1, 2), 2)
            fail("Expected capacity limit")
        } catch (_: IllegalArgumentException) { }
        assertEquals(1, buffer.size)
    }

    private fun archive(vararg entries: Pair<String, String>): ByteArray {
        val bytes = ByteArrayOutputStream()
        TarArchiveOutputStream(BZip2CompressorOutputStream(bytes)).use { tar -> entries.forEach { (name, text) ->
            val data = text.toByteArray()
            val entry = TarArchiveEntry(name).apply { size = data.size.toLong() }
            tar.putArchiveEntry(entry); tar.write(data); tar.closeArchiveEntry()
        } }
        return bytes.toByteArray()
    }

    @Test fun extracts_nested_model_with_known_content() {
        val dir = createTempDirectory("voice-tar-").toFile()
        try {
            extractModelArchive(ByteArrayInputStream(archive("model/am/final.mdl" to "known")), dir, "model", 100, 3)
            assertEquals("known", File(dir, "model/am/final.mdl").readText())
        } finally { dir.deleteRecursively() }
    }

    @Test fun rejects_tar_slip_wrong_root_and_backslash_paths() {
        val dir = createTempDirectory("voice-tar-").toFile()
        try {
            for (name in listOf("model/../../outside", "other/file", "model/../outside", "model\\file")) {
                try {
                    extractModelArchive(ByteArrayInputStream(archive(name to "unsafe")), dir, "model", 100, 5)
                    fail("Expected rejection: $name")
                } catch (_: IOException) { }
            }
            assertTrue(dir.listFiles().orEmpty().isEmpty())
        } finally { dir.deleteRecursively() }
    }

    @Test fun rejects_actual_expanded_bytes_and_excess_entries() {
        val dir = createTempDirectory("voice-tar-").toFile()
        try {
            try {
                extractModelArchive(ByteArrayInputStream(archive("model/file" to "123456")), dir, "model", 5, 3)
                fail("Expected size limit")
            } catch (_: IOException) { }
            try {
                extractModelArchive(ByteArrayInputStream(archive("model/a" to "a", "model/b" to "b")), dir, "model", 100, 1)
                fail("Expected entry limit")
            } catch (_: IOException) { }
        } finally { dir.deleteRecursively() }
    }

    @Test fun rejects_tar_symbolic_links() {
        val bytes = ByteArrayOutputStream()
        TarArchiveOutputStream(BZip2CompressorOutputStream(bytes)).use { tar ->
            val entry = TarArchiveEntry("model/link", org.apache.commons.compress.archivers.tar.TarConstants.LF_SYMLINK)
            entry.linkName = "../../outside"
            tar.putArchiveEntry(entry)
            tar.closeArchiveEntry()
        }
        val dir = createTempDirectory("voice-tar-").toFile()
        try {
            try {
                extractModelArchive(ByteArrayInputStream(bytes.toByteArray()), dir, "model", 100, 3)
                fail("Expected link rejection")
            } catch (_: IOException) { }
            assertTrue(dir.listFiles().orEmpty().isEmpty())
        } finally { dir.deleteRecursively() }
    }

    @Test fun cancelled_extraction_never_marks_model_ready() {
        val dir = createTempDirectory("voice-tar-").toFile()
        try {
            try {
                extractModelArchive(ByteArrayInputStream(archive("model/file" to "data")), dir, "model", 100, 3) {
                    throw java.util.concurrent.CancellationException("cancelled")
                }
                fail("Expected cancellation")
            } catch (_: java.util.concurrent.CancellationException) { }
            assertFalse(File(dir, "model/.ready").exists())
        } finally { dir.deleteRecursively() }
    }
    @Test fun compressed_input_uses_block_reads_and_reports_actual_extracted_bytes() {
        val compressed = archive("model/a" to "first", "model/b" to "second")
        var singleReads = 0
        var blockReads = 0
        val source = object : ByteArrayInputStream(compressed) {
            override fun read(): Int { singleReads++; return super.read() }
            override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                blockReads++; return super.read(buffer, offset, length)
            }
        }
        val dir = createTempDirectory("voice-buffer-").toFile()
        val progress = mutableListOf<Long>()
        try {
            extractModelArchive(source, dir, "model", 11, 2, onProgress = { progress.add(it) })
            assertEquals(0, singleReads)
            assertTrue(blockReads > 0)
            assertEquals(11L, progress.last())
            assertTrue(progress.zipWithNext().all { (a, b) -> b > a })
            assertEquals("second", File(dir, "model/b").readText())
        } finally { dir.deleteRecursively() }
    }

    @Test fun verified_download_survives_cancelled_extraction_and_can_retry() {
        val dir = createTempDirectory("voice-cache-").toFile()
        try {
            val archive = File(dir, "verified.tar.bz2").apply { writeBytes(archive("model/file" to "known")) }
            val sha = java.security.MessageDigest.getInstance("SHA-256").digest(archive.readBytes())
                .joinToString("") { "%02x".format(it) }
            assertTrue(verifiedArchive(archive, archive.length(), sha))
            val unpacked = File(dir, "staging").apply { mkdir() }
            try {
                archive.inputStream().use { source ->
                    extractModelArchive(source, unpacked, "model", 10, 2) {
                        throw java.util.concurrent.CancellationException("cancelled")
                    }
                }
                fail("Expected cancellation")
            } catch (_: java.util.concurrent.CancellationException) { }
            unpacked.deleteRecursively()
            assertTrue(verifiedArchive(archive, archive.length(), sha))
            archive.inputStream().use { extractModelArchive(it, unpacked, "model", 10, 2) }
            assertEquals("known", File(unpacked, "model/file").readText())
        } finally { dir.deleteRecursively() }
    }

    @Test fun cached_download_rejects_changed_content_even_with_same_size() {
        val dir = createTempDirectory("voice-cache-").toFile()
        try {
            val file = File(dir, "archive").apply { writeText("abc") }
            val sha = java.security.MessageDigest.getInstance("SHA-256").digest(file.readBytes())
                .joinToString("") { "%02x".format(it) }
            file.writeText("bad")
            assertFalse(verifiedArchive(file, 3, sha))
            assertFalse(file.exists())
            file.writeText("ab")
            assertFalse(verifiedArchive(file, 3, sha))
            assertFalse(file.exists())
        } finally { dir.deleteRecursively() }
    }

    @Test fun install_errors_describe_installation_not_microphone_or_dictation() {
        assertTrue(modelInstallFailureMessage(OutOfMemoryError()).contains("распаковки"))
        assertTrue(modelInstallFailureMessage(NoClassDefFoundError("compress")).contains("распаковки"))
        assertTrue(modelInstallFailureMessage(IOException("ENOSPC")).contains("места"))
        assertTrue(modelInstallFailureMessage(IOException("corrupt")).contains("corrupt"))
    }

}
