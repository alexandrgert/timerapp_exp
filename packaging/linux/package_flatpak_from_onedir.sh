#!/usr/bin/env bash
# packaging/linux/package_flatpak_from_onedir.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
VERSION="${VERSION:?VERSION required}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
APP_ID="com.timerapp.exp"
FLATPAK_ARCH="x86_64"
RUNTIME_BRANCH="24.08"
RUNTIME_REF="org.freedesktop.Platform/${FLATPAK_ARCH}/${RUNTIME_BRANCH}"
SDK_REF="org.freedesktop.Sdk/${FLATPAK_ARCH}/${RUNTIME_BRANCH}"
FLATPAK_DIR="$PROJECT_DIR/packaging/linux/flatpak"
OUT="${DIST_DIR}/timerapp-exp-${VERSION}-x86_64.flatpak"

require_x86_64_host() {
  case "$(uname -m)" in
    x86_64) ;;
    *)
      echo "Error: Flatpak packaging requires an x86_64 (amd64) host; got $(uname -m)." >&2
      exit 1
      ;;
  esac
}

if [[ -n "${ARCH:-}" && "${ARCH}" != "amd64" && "${ARCH}" != "x86_64" ]]; then
  echo "Unsupported ARCH=${ARCH}; expected amd64 or x86_64." >&2
  exit 1
fi

require_x86_64_host

[[ -x "$ONEDIR/TaskTimer" ]] || { echo "Missing onedir" >&2; exit 1; }
command -v flatpak >/dev/null

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
builddir="$work/build"
repo="$work/repo"
source_dir="$work/source"

# Flatpak's build sandbox cannot reliably access arbitrary host paths.
mkdir -p "$source_dir/onedir"
cp -a "$ONEDIR/." "$source_dir/onedir/"
cp "$FLATPAK_DIR/com.timerapp.exp.desktop" "$source_dir/"
cp "$FLATPAK_DIR/com.timerapp.exp.metainfo.xml" "$source_dir/"
cp "$PROJECT_DIR/packaging/linux/tasktimer.svg" "$source_dir/"

flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install -y --user --arch="$FLATPAK_ARCH" flathub "$RUNTIME_REF" "$SDK_REF"

flatpak build-init --arch="$FLATPAK_ARCH" "$builddir" "$APP_ID" \
  "org.freedesktop.Sdk/${FLATPAK_ARCH}" "org.freedesktop.Platform/${FLATPAK_ARCH}" "$RUNTIME_BRANCH"

# Install binary tree under /app
flatpak build "$builddir" mkdir -p /app/lib/timerapp-exp /app/bin /app/share/applications \
  /app/share/icons/hicolor/scalable/apps /app/share/metainfo
flatpak build --bind-mount=/run/host-source="$source_dir" "$builddir" \
  cp -a /run/host-source/onedir/. /app/lib/timerapp-exp/
flatpak build "$builddir" bash -c 'printf "%s\n" "#!/bin/sh" "exec /app/lib/timerapp-exp/TaskTimer \"\$@\"" > /app/bin/com.timerapp.exp && chmod 755 /app/bin/com.timerapp.exp'
flatpak build --bind-mount=/run/host-source="$source_dir" "$builddir" \
  cp /run/host-source/com.timerapp.exp.desktop /app/share/applications/
flatpak build --bind-mount=/run/host-source="$source_dir" "$builddir" \
  cp /run/host-source/com.timerapp.exp.metainfo.xml /app/share/metainfo/
flatpak build --bind-mount=/run/host-source="$source_dir" "$builddir" \
  cp /run/host-source/tasktimer.svg \
  /app/share/icons/hicolor/scalable/apps/com.timerapp.exp.svg

flatpak build-finish "$builddir" \
  --command=com.timerapp.exp \
  --share=network \
  --socket=x11 --socket=wayland --socket=fallback-x11 \
  --socket=session-bus \
  --device=dri \
  --filesystem=home

mkdir -p "$repo"
flatpak build-export "$repo" "$builddir"
mkdir -p "$DIST_DIR"
flatpak build-bundle --arch="$FLATPAK_ARCH" "$repo" "$OUT" "$APP_ID" \
  --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo

echo "Готово: $OUT"
ls -lh "$OUT"
file "$OUT"
