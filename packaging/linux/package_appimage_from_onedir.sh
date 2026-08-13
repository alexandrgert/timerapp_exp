#!/usr/bin/env bash
# Build an AppImage from the PyInstaller onedir output.
#
# Task 6 / CI tool downloads (continuous x86_64 releases):
# https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
# https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGING_DIR="$PROJECT_DIR/packaging/linux"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
VERSION="${VERSION:?VERSION required}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
LINUXDEPLOY="${LINUXDEPLOY:-linuxdeploy}"
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"

if [[ ! "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z._+-]*$ ]]; then
  echo "Invalid VERSION: $VERSION" >&2
  exit 1
fi

if [[ ! -x "$ONEDIR/TaskTimer" ]]; then
  echo "Missing onedir binary: $ONEDIR/TaskTimer" >&2
  exit 1
fi

resolve_tool() {
  local tool="$1"
  local env_name="$2"

  if [[ "$tool" == */* ]]; then
    if [[ ! -x "$tool" ]]; then
      echo "$env_name is not executable: $tool" >&2
      exit 1
    fi
    printf '%s\n' "$tool"
    return
  fi

  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing $env_name tool: $tool" >&2
    exit 1
  fi
  command -v "$tool"
}

linuxdeploy_path="$(resolve_tool "$LINUXDEPLOY" LINUXDEPLOY)"
appimagetool_path="$(resolve_tool "$APPIMAGETOOL" APPIMAGETOOL)"

mkdir -p "$DIST_DIR" "$PROJECT_DIR/build"
work_dir="$(mktemp -d "$PROJECT_DIR/build/appimage.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

app_dir="$work_dir/AppDir"
app_lib_dir="$app_dir/usr/lib/timerapp-exp"
mkdir -p "$app_lib_dir" "$app_dir/usr/bin"
cp -a "$ONEDIR/." "$app_lib_dir/"
ln -s ../lib/timerapp-exp/TaskTimer "$app_dir/usr/bin/TaskTimer"
app_icon="$work_dir/timerapp-exp.svg"
cp "$PACKAGING_DIR/tasktimer.svg" "$app_icon"

# AppImages are executable files themselves; extraction avoids requiring FUSE
# when the downloaded tools are AppImages in containers or CI runners.
APPIMAGE_EXTRACT_AND_RUN=1 "$linuxdeploy_path" \
  --appdir "$app_dir" \
  --desktop-file "$PACKAGING_DIR/appimage/timerapp-exp.desktop" \
  --icon-file "$app_icon"

cat > "$app_dir/AppRun" <<'EOF'
#!/bin/sh
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$APPDIR/usr/lib/timerapp-exp/TaskTimer" "$@"
EOF
chmod 755 "$app_dir/AppRun"

output="$DIST_DIR/timerapp-exp-${VERSION}-x86_64.AppImage"
rm -f "$output"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$appimagetool_path" "$app_dir" "$output"
chmod 755 "$output"

echo "Готово: $output"
ls -lh "$output"
