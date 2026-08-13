#!/usr/bin/env bash
# packaging/linux/package_rpm_from_staging.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="${STAGING_DIR:?STAGING_DIR required}"
VERSION="${VERSION:?VERSION required}"
PACKAGE_NAME="${PACKAGE_NAME:-timerapp-exp}"
TARGET_ARCH="${TARGET_ARCH:-amd64}"
MAINTAINER="${MAINTAINER:-alexandrgert <alexandrgert@gmail.com>}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
PACKAGE_TITLE="${PACKAGE_TITLE:-TaskTimer Experiment}"

if [[ ! -d "$STAGING_DIR" ]]; then
  echo "Missing staging directory: $STAGING_DIR" >&2
  exit 1
fi

if [[ "$TARGET_ARCH" != "amd64" && "$TARGET_ARCH" != "x86_64" ]]; then
  echo "Unsupported TARGET_ARCH=$TARGET_ARCH; expected amd64 or x86_64." >&2
  exit 1
fi

if ! command -v fpm >/dev/null 2>&1; then
  echo "Install fpm and rpm before building: sudo gem install fpm --no-document" >&2
  exit 1
fi

for required_path in opt usr; do
  if [[ ! -e "$STAGING_DIR/$required_path" ]]; then
    echo "Missing staging path: $STAGING_DIR/$required_path" >&2
    exit 1
  fi
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

rpm_arch="x86_64"
normalized_name="${PACKAGE_NAME}-${VERSION}-amd64.rpm"
requested_output="$work/$normalized_name"

fpm -s dir -t rpm \
  -C "$STAGING_DIR" \
  --name "$PACKAGE_NAME" \
  --version "$VERSION" \
  --architecture "$rpm_arch" \
  --description "$PACKAGE_TITLE. Experimental desktop task timer with Bitrix24 integration." \
  --maintainer "$MAINTAINER" \
  --category Applications/Productivity \
  --depends 'glibc >= 2.31' \
  --depends glib2 \
  --depends libX11 \
  --depends libxcb \
  --depends libxkbcommon \
  --depends dbus-libs \
  --depends fontconfig \
  --depends freetype \
  --depends libglvnd-glx \
  --depends libglvnd-egl \
  --depends libXext \
  --depends libXrender \
  --depends libXi \
  --depends libXrandr \
  --depends libXScrnSaver \
  --depends libXcursor \
  --depends libXinerama \
  --depends libtiff \
  -p "$requested_output" \
  opt usr

rpm_output="$requested_output"
if [[ ! -f "$rpm_output" ]]; then
  shopt -s nullglob
  rpm_candidates=(
    "$work/${PACKAGE_NAME}-${VERSION}"-*.x86_64.rpm
    "$work/${PACKAGE_NAME}-${VERSION}"-*.amd64.rpm
  )
  shopt -u nullglob
  if (( ${#rpm_candidates[@]} != 1 )); then
    echo "Unable to identify the RPM produced by fpm in $work." >&2
    exit 1
  fi
  rpm_output="${rpm_candidates[0]}"
fi

mkdir -p "$DIST_DIR"
normalized_output="$DIST_DIR/$normalized_name"
rm -f "$normalized_output"
mv "$rpm_output" "$normalized_output"

echo "Готово: $normalized_output"
ls -lh "$normalized_output"
