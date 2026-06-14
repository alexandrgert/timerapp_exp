#!/usr/bin/env bash
# Сборка .deb (amd64) для TaskTimer link B24: PyInstaller onedir + dpkg-deb.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
REPO_ROOT="$PROJECT_DIR"
PACKAGING_DIR="$PROJECT_DIR/packaging/linux"

PACKAGE_NAME="${PACKAGE_NAME:-tasktimer-link-b24}"
ARCH="${ARCH:-amd64}"
MAINTAINER="${PACKAGE_MAINTAINER:-alexandrgert <alexandrgert@gmail.com>}"
VENV="${VENV:-$PROJECT_DIR/.venv}"
PYTHON="${PYTHON:-$VENV/bin/python}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/tasktimer-link-b24}"
BIN_NAME="${BIN_NAME:-tasktimer-link-b24}"
BUMP="${BUMP:-patch}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Не найден Python в venv: $PYTHON" >&2
  echo "Создайте окружение: python -m venv $PROJECT_DIR/.venv && $PROJECT_DIR/.venv/bin/pip install -e $PROJECT_DIR -r $PROJECT_DIR/requirements-build.txt" >&2
  exit 1
fi

if [[ -z "${VERSION:-}" && "${NO_BUMP:-0}" != "1" ]]; then
  echo "==> Semver bump (${BUMP}) в pyproject.toml"
  "$PYTHON" "$PROJECT_DIR/scripts/bump_version.py" "$BUMP" >/dev/null
fi

VERSION="${VERSION:-$(
  "$PYTHON" -c "import tomllib; print(tomllib.load(open('$PROJECT_DIR/pyproject.toml','rb'))['project']['version'])"
)}"
echo "==> Версия пакета: ${VERSION}"
# Название продукта (без версии) — меню приложений, описание пакета.
PACKAGE_TITLE="${PACKAGE_TITLE:-TaskTimer link B24}"

# Имя файла: название + версия + архитектура.
DEB_FILE="${PACKAGE_NAME}-${VERSION}-${ARCH}.deb"
DIST_DIR="$PROJECT_DIR/dist"
DEB_OUT="$DIST_DIR/$DEB_FILE"

if [[ "$(uname -m)" != "x86_64" && "$ARCH" == "amd64" ]]; then
  echo "Предупреждение: сборка amd64 на $(uname -m); для релиза используйте x86_64." >&2
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "Установите dpkg-deb: sudo apt install dpkg" >&2
  exit 1
fi

echo "==> Установка зависимостей сборки"
"$PYTHON" -m pip install -q -e "$PROJECT_DIR" -r "$PROJECT_DIR/requirements-build.txt"

echo "==> PyInstaller (TaskTimer-linux.spec)"
cd "$PROJECT_DIR"
"$PYTHON" -m PyInstaller --noconfirm --clean TaskTimer-linux.spec

if [[ ! -x "$DIST_DIR/TaskTimer/TaskTimer" ]]; then
  echo "Не найден бинарник: $DIST_DIR/TaskTimer/TaskTimer" >&2
  exit 1
fi

BUILD_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$BUILD_ROOT"; }
trap cleanup EXIT

OPT_REL="${INSTALL_PREFIX#/}"
INSTALL_DIR="$BUILD_ROOT/$OPT_REL"
mkdir -p "$INSTALL_DIR"
cp -a "$DIST_DIR/TaskTimer/." "$INSTALL_DIR/"
echo "$VERSION" > "$INSTALL_DIR/VERSION"

mkdir -p "$BUILD_ROOT/usr/bin"
cat > "$BUILD_ROOT/usr/bin/$BIN_NAME" <<EOF
#!/bin/sh
exec ${INSTALL_PREFIX}/TaskTimer "\$@"
EOF
chmod 755 "$BUILD_ROOT/usr/bin/$BIN_NAME"

mkdir -p "$BUILD_ROOT/usr/share/applications"
cat > "$BUILD_ROOT/usr/share/applications/tasktimer-link-b24.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${PACKAGE_TITLE}
Name[ru]=${PACKAGE_TITLE}
Comment=Desktop task timer with Bitrix24 integration
Comment[ru]=Таймер задач с интеграцией Битрикс24
Exec=${BIN_NAME}
Icon=tasktimer-link-b24
Terminal=false
Categories=Office;Utility;
StartupWMClass=tasktimer-link-b24
EOF

mkdir -p "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps"
cp "$PACKAGING_DIR/tasktimer.svg" "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps/tasktimer-link-b24.svg"

INSTALLED_SIZE_KB="$(
  du -sk "$BUILD_ROOT/$OPT_REL" "$BUILD_ROOT/usr" 2>/dev/null | awk '{s += $1} END {print s}'
)"

mkdir -p "$BUILD_ROOT/DEBIAN"
cat > "$BUILD_ROOT/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE_KB}
Maintainer: ${MAINTAINER}
Conflicts: tasktimer
Replaces: tasktimer
Depends: libc6 (>= 2.31), libglib2.0-0, libx11-6, libxcb1, libxkbcommon0, libdbus-1-3, libfontconfig1, libfreetype6, libgl1, libegl1, libxext6, libxrender1, libxi6, libxrandr2, libxss1, libxcursor1, libxinerama1, libtiff5 | libtiff6
Description: ${PACKAGE_TITLE}
 Desktop task timer: daily plan, focus mode, Bitrix24 tasks and smart-process projects.
EOF

cat > "$BUILD_ROOT/DEBIAN/preinst" <<EOF
#!/bin/sh
set -e

PKG_NAME="${PACKAGE_NAME}"
NEW_VERSION="${VERSION}"

is_installed() {
  dpkg-query -W -f='\${Status}' "\$PKG_NAME" 2>/dev/null | grep -q "install ok installed"
}

installed_version() {
  dpkg-query -W -f='\${Version}' "\$PKG_NAME" 2>/dev/null
}

reject_downgrade() {
  old_version="\$1"
  if [ -z "\$old_version" ]; then
    return 0
  fi
  if dpkg --compare-versions "\$NEW_VERSION" lt "\$old_version"; then
    echo "Ошибка: уже установлена более новая версия \$PKG_NAME (\$old_version)." >&2
    echo "Пакет для установки: \$NEW_VERSION." >&2
    echo "Сначала удалите текущую версию:" >&2
    echo "  sudo apt remove \$PKG_NAME" >&2
    echo "Затем установите нужную версию (downgrade)." >&2
    exit 1
  fi
}

case "\$1" in
  install)
    if is_installed; then
      reject_downgrade "\$(installed_version)"
    fi
    ;;
  upgrade)
    reject_downgrade "\$2"
    ;;
esac

exit 0
EOF
chmod 755 "$BUILD_ROOT/DEBIAN/preinst"

cat > "$BUILD_ROOT/DEBIAN/postinst" <<EOF
#!/bin/sh
set -e

PKG_NAME="${PACKAGE_NAME}"
NEW_VERSION="${VERSION}"

case "\$1" in
  configure)
    if [ -n "\$2" ] && dpkg --compare-versions "\$NEW_VERSION" gt "\$2"; then
      echo "\${PACKAGE_TITLE} обновлён: \$2 -> \$NEW_VERSION"
    elif [ -n "\$2" ] && [ "\$NEW_VERSION" = "\$2" ]; then
      echo "\${PACKAGE_TITLE} переустановлен (версия \$NEW_VERSION)"
    fi
    ;;
esac

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$BUILD_ROOT/DEBIAN/postinst"

cat > "$BUILD_ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
  fi
fi
exit 0
EOF
chmod 755 "$BUILD_ROOT/DEBIAN/postrm"

mkdir -p "$DIST_DIR"
rm -f "$DEB_OUT"
dpkg-deb --build --root-owner-group "$BUILD_ROOT" "$DEB_OUT"

echo ""
echo "Готово: $DEB_OUT"
ls -lh "$DEB_OUT"
dpkg-deb -I "$DEB_OUT" | grep -E '^( Package| Version| Installed-Size| Maintainer):'
