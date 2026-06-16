#!/usr/bin/env bash
# Сборка macOS .app + .zip для TaskTimer link B24 (PyInstaller onedir + BUNDLE).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
VENV="${VENV:-$PROJECT_DIR/.venv}"
PYTHON="${PYTHON:-$VENV/bin/python}"
DIST_DIR="$PROJECT_DIR/dist"
PACKAGE_NAME="${PACKAGE_NAME:-tasktimer-link-b24}"
BUMP="${BUMP:-patch}"
APP_BUNDLE_NAME="TaskTimer link B24.app"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Ошибка: сборка macOS возможна только на macOS (Darwin)." >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Не найден Python в venv: $PYTHON" >&2
  exit 1
fi

if [[ -z "${VERSION:-}" && "${NO_BUMP:-0}" != "1" ]]; then
  echo "==> Semver bump (${BUMP}) в pyproject.toml"
  "$PYTHON" "$PROJECT_DIR/scripts/bump_version.py" "$BUMP" >/dev/null
fi

VERSION="${VERSION:-$(
  "$PYTHON" -c "import tomllib; print(tomllib.load(open('$PROJECT_DIR/pyproject.toml','rb'))['project']['version'])"
)}"
ARCH="$(uname -m)"
echo "==> Версия: ${VERSION}, архитектура: ${ARCH}"

echo "==> Установка зависимостей сборки"
"$PYTHON" -m pip install -q -e "$PROJECT_DIR" -r "$PROJECT_DIR/requirements-build.txt"

export APP_VERSION="$VERSION"
echo "==> PyInstaller (TaskTimer-macos.spec)"
cd "$PROJECT_DIR"
"$PYTHON" -m PyInstaller --noconfirm --clean TaskTimer-macos.spec

app_path="$DIST_DIR/$APP_BUNDLE_NAME"
if [[ ! -d "$app_path" ]]; then
  echo "Не найден bundle: $app_path" >&2
  exit 1
fi

echo "$VERSION" > "$app_path/Contents/MacOS/VERSION"

zip_name="${PACKAGE_NAME}-${VERSION}-macos-${ARCH}.zip"
zip_out="$DIST_DIR/$zip_name"
rm -f "$zip_out"
(
  cd "$DIST_DIR"
  ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE_NAME" "$zip_name"
)

echo "Готово:"
ls -lh "$zip_out"
echo "Установка: распакуйте zip и перетащите «TaskTimer link B24.app» в Программы."
