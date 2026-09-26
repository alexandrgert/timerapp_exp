package com.timerapp.linkb24.voice

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory

class VoiceInputTest {
    @Test fun dictation_appends_without_erasing_existing_text_or_newline() {
        assertEquals("старое новый текст", appendDictation("старое", " новый текст "))
        assertEquals("старое\nновый текст", appendDictation("старое\n", "новый текст"))
        assertEquals("  старое  ", appendDictation("  старое  ", " "))
        assertEquals("новый текст", appendDictation("", "новый текст"))
    }

    @Test fun recognition_segments_and_partial_use_distinct_json_fields() {
        assertEquals("тест комментария", recognizedText("""{"text":"тест комментария"}"""))
        assertEquals("ещё слово", recognizedText("""{"partial":"ещё слово"}""", true))
        assertEquals("", recognizedText("""{"partial":"ещё слово"}"""))
        assertEquals("", recognizedText("bad json"))
    }

    private fun zip(vararg entries: Pair<String, String>): ByteArray {
        val bytes = ByteArrayOutputStream()
        ZipOutputStream(bytes).use { zip -> entries.forEach { (name, text) ->
            zip.putNextEntry(ZipEntry(name)); zip.write(text.toByteArray()); zip.closeEntry()
        } }
        return bytes.toByteArray()
    }

    @Test fun extracts_nested_model_with_known_content() {
        val dir = createTempDirectory("voice-zip-").toFile()
        try {
            extractModelArchive(ByteArrayInputStream(zip("model/am/final.mdl" to "known")), dir, "model", 100, 3)
            assertEquals("known", File(dir, "model/am/final.mdl").readText())
        } finally { dir.deleteRecursively() }
    }

    @Test fun rejects_zip_slip_absolute_wrong_root_and_backslash_paths() {
        val dir = createTempDirectory("voice-zip-").toFile()
        try {
            for (name in listOf("model/../../outside", "/model/file", "other/file", "model/../outside", "model\\file")) {
                try {
                    extractModelArchive(ByteArrayInputStream(zip(name to "unsafe")), dir, "model", 100, 5)
                    fail("Expected rejection: $name")
                } catch (_: IOException) { }
            }
            assertTrue(dir.listFiles().orEmpty().isEmpty())
        } finally { dir.deleteRecursively() }
    }

    @Test fun rejects_actual_expanded_bytes_and_excess_entries() {
        val dir = createTempDirectory("voice-zip-").toFile()
        try {
            try {
                extractModelArchive(ByteArrayInputStream(zip("model/file" to "123456")), dir, "model", 5, 3)
                fail("Expected size limit")
            } catch (_: IOException) { }
            try {
                extractModelArchive(ByteArrayInputStream(zip("model/a" to "a", "model/b" to "b")), dir, "model", 100, 1)
                fail("Expected entry limit")
            } catch (_: IOException) { }
        } finally { dir.deleteRecursively() }
    }

    @Test fun cancelled_extraction_never_marks_model_ready() {
        val dir = createTempDirectory("voice-zip-").toFile()
        try {
            try {
                extractModelArchive(ByteArrayInputStream(zip("model/file" to "data")), dir, "model", 100, 3) {
                    throw java.util.concurrent.CancellationException("cancelled")
                }
                fail("Expected cancellation")
            } catch (_: java.util.concurrent.CancellationException) { }
            assertFalse(File(dir, "model/.ready").exists())
        } finally { dir.deleteRecursively() }
    }
}
