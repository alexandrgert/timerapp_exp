#!/usr/bin/env bash
# Run only on the GitHub-hosted Android preview runner.
set -euo pipefail

sdk_root="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/usr/local/lib/android/sdk}}"
sdk_manager="$sdk_root/cmdline-tools/latest/bin/sdkmanager"
avd_manager="$sdk_root/cmdline-tools/latest/bin/avdmanager"
adb_command="$sdk_root/platform-tools/adb"
emulator_command="$sdk_root/emulator/emulator"
export ANDROID_SERIAL=emulator-5554
avd_name=tasktimer-preview
# Use one explicit location for both SDK avdmanager and emulator discovery.
export ANDROID_USER_HOME="${RUNNER_TEMP:?GitHub runner temporary directory is required}/tasktimer-preview-android"
export ANDROID_EMULATOR_HOME="$ANDROID_USER_HOME"
export ANDROID_AVD_HOME="$ANDROID_USER_HOME/avd"
mkdir -p "$ANDROID_AVD_HOME"
stage='SDK installation'
emulator_pid=''

cleanup() {
  result=$?
  trap - EXIT
  set +e
  if [[ "$result" -ne 0 ]]; then
    echo "Error: Android UI failed during $stage (exit $result)."
    if [[ "$stage" == 'emulator boot' && -f preview-emulator.log ]]; then
      tail -n 15 preview-emulator.log
    fi
  fi
  if [[ -n "$emulator_pid" ]]; then
    timeout 15 "$adb_command" -s "$ANDROID_SERIAL" emu kill >/dev/null 2>&1
    kill "$emulator_pid" >/dev/null 2>&1
  fi
  exit "$result"
}
trap cleanup EXIT

"$sdk_manager" --sdk_root="$sdk_root" 'emulator' 'system-images;android-35;google_apis;x86_64'
stage='AVD creation'
echo no | "$avd_manager" create avd --force --name "$avd_name" --path "$ANDROID_AVD_HOME/$avd_name.avd" --package 'system-images;android-35;google_apis;x86_64'
if [[ ! -f "$ANDROID_AVD_HOME/$avd_name.ini" ]]; then
  echo "Error: AVD creation did not produce $ANDROID_AVD_HOME/$avd_name.ini."
  exit 1
fi
"$emulator_command" -list-avds

stage='emulator boot'
"$emulator_command" -avd "$avd_name" -port 5554 -no-window -no-audio -no-boot-anim -no-snapshot -gpu swiftshader_indirect -accel on -cores 2 -memory 2048 >preview-emulator.log 2>&1 &
emulator_pid=$!
booted=false
boot_deadline=$((SECONDS + 240))
while (( SECONDS < boot_deadline )); do
  if ! kill -0 "$emulator_pid" 2>/dev/null; then
    echo 'Error: Android emulator exited before boot completed.'
    exit 1
  fi
  if [[ "$(timeout 5 "$adb_command" -s "$ANDROID_SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == '1' ]]; then
    booted=true
    break
  fi
  sleep 2
done
if [[ "$booted" != true ]]; then
  echo 'Error: Android emulator did not finish booting within the allowed time.'
  exit 1
fi

stage='device preparation'
"$adb_command" -s "$ANDROID_SERIAL" shell settings put global window_animation_scale 0
"$adb_command" -s "$ANDROID_SERIAL" shell settings put global transition_animation_scale 0
"$adb_command" -s "$ANDROID_SERIAL" shell settings put global animator_duration_scale 0
"$adb_command" -s "$ANDROID_SERIAL" shell input keyevent 82
stage='instrumentation tests'
bash ./gradlew --no-daemon :app:connectedDebugAndroidTest
