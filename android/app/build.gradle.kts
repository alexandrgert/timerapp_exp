import java.util.Properties
import java.net.URI
import java.security.MessageDigest
import java.nio.file.Files
import java.nio.file.StandardCopyOption

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

val keystoreProperties = Properties().apply {
    val keystorePropertiesFile = rootProject.file("keystore.properties")
    if (keystorePropertiesFile.isFile) {
        keystorePropertiesFile.inputStream().use { load(it) }
    }
}

// Official prebuilt Android library; downloaded only by an explicitly approved build.
// Pin both release and bytes: never compile against a moving/unverified binary.
val sherpaAar = layout.buildDirectory.file("verified-dependencies/sherpa-onnx-static-link-onnxruntime-1.13.8.aar")
val sherpaSha256 = "b22c3fc1b6a45666d28892bb2f7694beeb77a8362d7ebd77c1a5431ec9435471"
fun sha256(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input ->
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val size = input.read(buffer)
            if (size < 0) break
            digest.update(buffer, 0, size)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}
val prepareSherpaAar by tasks.registering {
    outputs.file(sherpaAar)
    outputs.upToDateWhen { sherpaAar.get().asFile.let { it.isFile && sha256(it) == sherpaSha256 } }
    doLast {
        val output = sherpaAar.get().asFile
        if (output.isFile && sha256(output) == sherpaSha256) return@doLast
        check(!gradle.startParameter.isOffline) { "Pinned sherpa-onnx AAR is not cached; an approved online GitHub build is required." }
        output.parentFile.mkdirs()
        val temporary = File(output.parentFile, "${output.name}.partial")
        try {
            val connection = URI("https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-static-link-onnxruntime-1.13.8.aar").toURL().openConnection()
            connection.connectTimeout = 30_000
            connection.readTimeout = 30_000
            connection.getInputStream().use { input -> temporary.outputStream().use { target ->
                val buffer = ByteArray(64 * 1024)
                var total = 0L
                while (true) {
                    val size = input.read(buffer)
                    if (size < 0) break
                    total += size
                    check(total <= 38_691_998L) { "Unexpected sherpa-onnx AAR size" }
                    target.write(buffer, 0, size)
                }
                check(total == 38_691_998L) { "Incomplete sherpa-onnx AAR download" }
            } }
            check(sha256(temporary) == sherpaSha256) { "sherpa-onnx AAR checksum mismatch" }
            Files.move(temporary.toPath(), output.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        } finally {
            temporary.delete()
        }
    }
}

android {
    namespace = "com.timerapp.linkb24"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.timerapp.exp"
        minSdk = 29
        targetSdk = 35
        versionCode = 1108
        versionName = "0.11.8"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    signingConfigs {
        create("release") {
            val storeFilePath = keystoreProperties.getProperty("storeFile")
            // Debug/preview builds do not require production signing credentials.
            // Android's validateSigningRelease still rejects release builds without a keystore.
            storeFile = storeFilePath?.takeIf { it.isNotBlank() }?.let { rootProject.file(it) }
            storePassword = keystoreProperties.getProperty("storePassword")
            keyAlias = keystoreProperties.getProperty("keyAlias")
            keyPassword = keystoreProperties.getProperty("keyPassword")
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".preview"
            versionNameSuffix = "-preview"
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    sourceSets.getByName("test").resources.srcDir("../../tests/fixtures")

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-process:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation(files(sherpaAar).builtBy(prepareSherpaAar))
    implementation("org.apache.commons:commons-compress:1.27.1")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}
