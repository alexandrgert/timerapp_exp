#!/usr/bin/env bash
# Build the full Linux package matrix from an existing PyInstaller onedir.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGING_DIR="$PROJECT_DIR/packaging/linux"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"

if [[ ! -x "$ONEDIR/TaskTimer" ]]; then
  echo "Missing onedir binary: $ONEDIR/TaskTimer" >&2
  exit 1
fi

VERSION="${VERSION:-$(
  python3 -c "import tomllib; print(tomllib.load(open('$PROJECT_DIR/pyproject.toml','rb'))['project']['version'])"
)}"
STAGING_DIR="$(mktemp -d)"
cleanup_staging() {
  rm -rf "$STAGING_DIR"
}
trap cleanup_staging EXIT

export VERSION STAGING_DIR ONEDIR DIST_DIR
"$PACKAGING_DIR/stage_from_pyinstaller.sh"
"$PACKAGING_DIR/package_tarballs_from_staging.sh"
"$PACKAGING_DIR/package_rpm_from_staging.sh"
"$PACKAGING_DIR/package_appimage_from_onedir.sh"
"$PACKAGING_DIR/package_flatpak_from_onedir.sh"
"$PACKAGING_DIR/package_snap_from_onedir.sh"
"$PACKAGING_DIR/package_ebuild_from_staging.sh"
"$PACKAGING_DIR/package_pisi_from_staging.sh"
"$PACKAGING_DIR/package_pet_from_staging.sh"
"$PACKAGING_DIR/package_lzm_from_staging.sh"
