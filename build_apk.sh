#!/usr/bin/env bash
# Сборка APK TaskTimer link B24 (Android 10+, API 29).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
ANDROID_DIR="$PROJECT_DIR/android"
DIST_DIR="$PROJECT_DIR/dist"
SDK_ROOT="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$ANDROID_DIR/.android-sdk}}"
CMDLINE_TOOLS="$SDK_ROOT/cmdline-tools/latest"
GRADLE_VERSION="8.11.1"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Не найдено: $1" >&2
    exit 1
  fi
}

ensure_jdk17() {
  local jdk_dir="$ANDROID_DIR/.jdk17"
  if [[ -x "$jdk_dir/bin/java" ]]; then
    export JAVA_HOME="$jdk_dir"
    export PATH="$JAVA_HOME/bin:$PATH"
    return
  fi

  echo "==> Установка JDK 17 (Eclipse Temurin) — Android Gradle не поддерживает Java 25"
  mkdir -p "$jdk_dir"
  local archive="/tmp/temurin-jdk17.tar.gz"
  curl -fsSL \
    "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse?project=jdk" \
    -o "$archive"
  rm -rf "$jdk_dir"/*
  tar -xzf "$archive" -C "$jdk_dir" --strip-components=1
  export JAVA_HOME="$jdk_dir"
  export PATH="$JAVA_HOME/bin:$PATH"
  java -version
}

ensure_gradle_wrapper() {
  if [[ -x "$ANDROID_DIR/gradlew" ]] && [[ -f "$ANDROID_DIR/gradle/wrapper/gradle-wrapper.jar" ]]; then
    return
  fi

  echo "==> Подготовка Gradle Wrapper ${GRADLE_VERSION}"
  mkdir -p "$ANDROID_DIR/gradle/wrapper"
  local gradle_zip="/tmp/gradle-${GRADLE_VERSION}-bin.zip"
  if [[ ! -f "$gradle_zip" ]]; then
    curl -fsSL "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -o "$gradle_zip"
  fi
  local gradle_home="/tmp/gradle-${GRADLE_VERSION}"
  rm -rf "$gradle_home"
  unzip -q "$gradle_zip" -d /tmp
  "$gradle_home/bin/gradle" -p "$ANDROID_DIR" wrapper --gradle-version "$GRADLE_VERSION"
}

install_android_sdk() {
  mkdir -p "$SDK_ROOT"
  if [[ ! -x "$CMDLINE_TOOLS/bin/sdkmanager" ]]; then
    echo "==> Установка Android command-line tools"
    local tools_zip="/tmp/android-cmdline-tools.zip"
    curl -fsSL "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip" -o "$tools_zip"
    rm -rf "$SDK_ROOT/cmdline-tools"
    mkdir -p "$SDK_ROOT/cmdline-tools"
    unzip -q "$tools_zip" -d "$SDK_ROOT/cmdline-tools"
    mv "$SDK_ROOT/cmdline-tools/cmdline-tools" "$SDK_ROOT/cmdline-tools/latest"
  fi

  yes | "$CMDLINE_TOOLS/bin/sdkmanager" --sdk_root="$SDK_ROOT" --licenses >/dev/null || true
  "$CMDLINE_TOOLS/bin/sdkmanager" --sdk_root="$SDK_ROOT" \
    "platform-tools" \
    "platforms;android-35" \
    "platforms;android-29" \
    "build-tools;35.0.0"
}

write_local_properties() {
  cat >"$ANDROID_DIR/local.properties" <<EOF
sdk.dir=$SDK_ROOT
EOF
}

build_apk() {
  export ANDROID_HOME="$SDK_ROOT"
  export ANDROID_SDK_ROOT="$SDK_ROOT"

  write_local_properties
  cd "$ANDROID_DIR"
  chmod +x gradlew
  ./gradlew --no-daemon assembleRelease

  mkdir -p "$DIST_DIR"
  local version
  version="$(grep 'versionName' app/build.gradle.kts | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
  cp -f app/build/outputs/apk/release/app-release.apk \
    "$DIST_DIR/tasktimer-link-b24-${version}-android.apk"

  echo "Готово:"
  ls -lh "$DIST_DIR/tasktimer-link-b24-${version}-android.apk"
}

require_cmd java
require_cmd curl
require_cmd unzip
ensure_jdk17
ensure_gradle_wrapper
install_android_sdk
build_apk
