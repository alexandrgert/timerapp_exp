#!/usr/bin/env bash
# Build an AppImage from the PyInstaller onedir output.
#
# PyInstaller already bundles Qt/libs — do NOT run linuxdeploy (it rescans
# system deps and fails on incomplete runner packages).
#
# CI downloads pinned release (keep in sync with .github/workflows/ci.yml):
# https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
# SHA-256: ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGING_DIR="$PROJECT_DIR/packaging/linux"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
VERSION="${VERSION:?VERSION required}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
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

appimagetool_path="$(resolve_tool "$APPIMAGETOOL" APPIMAGETOOL)"

mkdir -p "$DIST_DIR" "$PROJECT_DIR/build"
work_dir="$(mktemp -d "$PROJECT_DIR/build/appimage.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

app_dir="$work_dir/AppDir"
app_lib_dir="$app_dir/usr/lib/timerapp-exp"
mkdir -p "$app_lib_dir" "$app_dir/usr/bin" "$app_dir/usr/share/icons/hicolor/scalable/apps"
cp -a "$ONEDIR/." "$app_lib_dir/"
ln -sf ../lib/timerapp-exp/TaskTimer "$app_dir/usr/bin/TaskTimer"
cp "$PACKAGING_DIR/appimage/timerapp-exp.desktop" "$app_dir/timerapp-exp.desktop"
cp "$PACKAGING_DIR/tasktimer.svg" "$app_dir/timerapp-exp.svg"
cp "$PACKAGING_DIR/tasktimer.svg" \
  "$app_dir/usr/share/icons/hicolor/scalable/apps/timerapp-exp.svg"

# appimagetool expects Icon= name matching a file beside the desktop entry
sed -i 's/^Icon=.*/Icon=timerapp-exp/' "$app_dir/timerapp-exp.desktop"

cat > "$app_dir/AppRun" <<'EOF'
#!/bin/sh
APPDIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$APPDIR/usr/lib/timerapp-exp/TaskTimer" "$@"
EOF
chmod 755 "$app_dir/AppRun"

output="$DIST_DIR/timerapp-exp-${VERSION}-x86_64.AppImage"
rm -f "$output"
# Extraction mode: no FUSE required in CI containers.
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$appimagetool_path" "$app_dir" "$output"
chmod 755 "$output"

echo "Готово: $output"
ls -lh "$output"
