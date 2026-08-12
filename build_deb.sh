#!/usr/bin/env bash
# Сборка .deb для TaskTimer Experiment (Linux amd64): PyInstaller onedir + dpkg-deb.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
PACKAGING_DIR="$PROJECT_DIR/packaging/linux"

PACKAGE_NAME="${PACKAGE_NAME:-timerapp-exp}"
TARGET_ARCH=amd64
MAINTAINER="${PACKAGE_MAINTAINER:-alexandrgert <alexandrgert@gmail.com>}"
VENV="${VENV:-$PROJECT_DIR/.venv}"
PYTHON="${PYTHON:-$VENV/bin/python}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/timerapp_exp}"
BIN_NAME="${BIN_NAME:-timerapp-exp}"
BUMP="${BUMP:-patch}"
DIST_DIR="$PROJECT_DIR/dist"
OFFLINE="${OFFLINE:-0}"
ALLOW_NO_BUMP="${ALLOW_NO_BUMP:-0}"

require_amd64_host() {
  case "$(uname -m)" in
    x86_64) ;;
    *)
      echo "Ошибка: сборка .deb поддерживается только на x86_64 (amd64)." >&2
      exit 1
      ;;
  esac
}

if [[ -n "${ARCH:-}" && "${ARCH}" != "amd64" ]]; then
  echo "Неподдерживаемая ARCH=${ARCH}. Допустимо только amd64." >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Не найден Python в venv: $PYTHON" >&2
  exit 1
fi

if [[ -z "${VERSION:-}" ]]; then
  if [[ "${NO_BUMP:-0}" == "1" && "$ALLOW_NO_BUMP" != "1" ]]; then
    echo "NO_BUMP=1 игнорируется: для сборок версия всегда поднимается минимум на patch." >&2
    echo "Если нужно явно отключить bump, используйте ALLOW_NO_BUMP=1 NO_BUMP=1." >&2
  fi
  if [[ "${NO_BUMP:-0}" != "1" || "$ALLOW_NO_BUMP" != "1" ]]; then
    echo "==> Semver bump (${BUMP}) в pyproject.toml"
    "$PYTHON" "$PROJECT_DIR/scripts/bump_version.py" "$BUMP" >/dev/null
  fi
fi

VERSION="${VERSION:-$(
  "$PYTHON" -c "import tomllib; print(tomllib.load(open('$PROJECT_DIR/pyproject.toml','rb'))['project']['version'])"
)}"
echo "==> Версия пакета: ${VERSION}"

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "Установите dpkg-deb: sudo apt install dpkg" >&2
  exit 1
fi

require_amd64_host

if [[ "$OFFLINE" == "1" ]]; then
  echo "==> OFFLINE=1: пропускаю установку зависимостей сборки"
else
  echo "==> Установка зависимостей сборки"
  "$PYTHON" -m pip install -q -e "$PROJECT_DIR" -r "$PROJECT_DIR/requirements-build.txt"
fi

deb_file="${PACKAGE_NAME}-${VERSION}-${TARGET_ARCH}.deb"
PACKAGE_TITLE="${PACKAGE_TITLE:-TaskTimer Experiment}"

echo "==> Сборка ${deb_file}"

echo "==> PyInstaller (TaskTimer-linux.spec)"
cd "$PROJECT_DIR"
"$PYTHON" -m PyInstaller --noconfirm --clean TaskTimer-linux.spec

STAGING_DIR="$(mktemp -d)"
cleanup_staging() {
  rm -rf "$STAGING_DIR"
}
trap cleanup_staging EXIT

export STAGING_DIR VERSION INSTALL_PREFIX BIN_NAME PACKAGE_TITLE PACKAGING_DIR
export PACKAGE_NAME TARGET_ARCH MAINTAINER DIST_DIR
"$PACKAGING_DIR/stage_from_pyinstaller.sh"
"$PACKAGING_DIR/package_deb_from_staging.sh"

rm -rf "$STAGING_DIR"
trap - EXIT
