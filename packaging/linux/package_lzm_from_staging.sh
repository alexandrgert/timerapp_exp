#!/usr/bin/env bash
# packaging/linux/package_lzm_from_staging.sh
# Experimental Slax LZM packager from staging tree.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="${STAGING_DIR:?STAGING_DIR required}"
VERSION="${VERSION:?VERSION required}"
PACKAGE_NAME="${PACKAGE_NAME:-timerapp-exp}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
TARGET_ARCH="${TARGET_ARCH:-amd64}"

if [[ ! -d "$STAGING_DIR" ]]; then
  echo "Missing staging directory: $STAGING_DIR" >&2
  exit 1
fi
STAGING_DIR="$(cd "$STAGING_DIR" && pwd)"

for required_path in opt usr; do
  if [[ ! -e "$STAGING_DIR/$required_path" ]]; then
    echo "Missing staging path: $STAGING_DIR/$required_path" >&2
    exit 1
  fi
done

if ! command -v mksquashfs >/dev/null 2>&1; then
  echo "Missing required tool: mksquashfs (install squashfs-tools)" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"
DIST_DIR="$(cd "$DIST_DIR" && pwd)"

output="${DIST_DIR}/${PACKAGE_NAME}-${VERSION}-${TARGET_ARCH}.lzm"
rm -f "$output"

mksquashfs "$STAGING_DIR" "$output" -comp xz -noappend

if ! file "$output" | grep -qi 'squashfs'; then
  echo "Unexpected file type for $output" >&2
  exit 1
fi

if command -v unsquashfs >/dev/null 2>&1; then
  listing="$(mktemp)"
  unsquashfs -l "$output" > "$listing"
  for required_member in usr/bin/timerapp-exp usr/share/applications/timerapp-exp.desktop; do
    if ! grep -Fq "$required_member" "$listing"; then
      rm -f "$listing"
      echo "Missing $required_member in $output" >&2
      exit 1
    fi
  done
  rm -f "$listing"
fi

echo "Готово: $output"
ls -lh "$output"
