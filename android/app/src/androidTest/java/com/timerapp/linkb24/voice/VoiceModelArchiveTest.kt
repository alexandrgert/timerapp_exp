package com.timerapp.linkb24.voice

import android.util.Base64
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.UUID

/** Tiny Python tarfile USTAR/bz2 fixture, independent from Commons writer. No network/model download. */
class VoiceModelArchiveTest {
    @Test fun bzip2_extracts_on_android_storage_and_reports_bytes() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(context.cacheDir, "voice-archive-test-${UUID.randomUUID()}").apply { mkdir() }
        try {
            val archive = File(root, "fixture.tar.bz2").apply { writeBytes(Base64.decode(FIXTURE, Base64.DEFAULT)) }
            val progress = mutableListOf<Long>()
            archive.inputStream().use { input ->
                extractModelArchive(input, File(root, "unpacked"), "model", 21, 2,
                    onProgress = { progress.add(it) })
            }
            assertEquals("fixture-encoder", File(root, "unpacked/model/encoder.int8.onnx").readText())
            assertEquals("tokens", File(root, "unpacked/model/tokens.txt").readText())
            assertEquals(21L, progress.last())
            assertTrue(progress.zipWithNext().all { (a, b) -> b > a })
        } finally { root.deleteRecursively() }
    }

    companion object {
        private const val FIXTURE = "QlpoOTFBWSZTWZSjyz0AAJb/gcuAAEBAA/fAACBAAG8vnkAAAQgIIACSCVCAAAABo0ZBJKanppNA0zKYRoxMmm+2vQcw31gA1nSQiUXkSkJP6lJQIQwDLGi3lmWEAUBgRfg4ReuBGbDuVEz/EB88nAww9CxZtwweHdMjNBblDyT6ho0rJYWiXRCRqllVr8cjiJVGIhAfi7kinChISlHlnoA="
    }
}
