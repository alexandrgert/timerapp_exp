#!/usr/bin/env bash
# packaging/linux/package_pet_from_staging.sh
# Experimental Puppy Linux PET and PUP packagers from staging tree.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="${STAGING_DIR:?STAGING_DIR required}"
VERSION="${VERSION:?VERSION required}"
PACKAGE_NAME="${PACKAGE_NAME:-timerapp-exp}"
PACKAGE_TITLE="${PACKAGE_TITLE:-TaskTimer Experiment}"
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

if ! command -v tar >/dev/null 2>&1; then
  echo "Missing required tool: tar" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"
DIST_DIR="$(cd "$DIST_DIR" && pwd)"

rootname="${PACKAGE_NAME}-${VERSION}-${TARGET_ARCH}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/$rootname"
cp -a "$STAGING_DIR/." "$work/$rootname/"
printf '%s\n' \
  "${PACKAGE_NAME}|${VERSION}||Official|1024K||${rootname}.pet||${PACKAGE_TITLE}||||" \
  > "$work/$rootname/pet.specs"

pet_output="${DIST_DIR}/${rootname}.pet"
pup_output="${DIST_DIR}/${rootname}.pup"
rm -f "$pet_output" "$pup_output"

tar -C "$work" -czf "$pet_output" "$rootname"
tar -C "$work" -czf "$pup_output" "$rootname"

for output in "$pet_output" "$pup_output"; do
  listing="$work/listing-$(basename "$output").txt"
  tar -tzf "$output" > "$listing"
  for required_member in "${rootname}/pet.specs" "${rootname}/usr/bin/timerapp-exp"; do
    if ! grep -Fq "$required_member" "$listing"; then
      echo "Missing $required_member in $output" >&2
      exit 1
    fi
  done
  if ! file "$output" | grep -qi 'gzip compressed'; then
    echo "Unexpected file type for $output" >&2
    exit 1
  fi
done

echo "Готово: $pet_output"
echo "Готово: $pup_output"
ls -lh "$pet_output" "$pup_output"
