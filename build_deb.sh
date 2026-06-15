#!/usr/bin/env bash
# Сборка .deb для TaskTimer link B24 (Linux amd64): PyInstaller onedir + dpkg-deb.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
PACKAGING_DIR="$PROJECT_DIR/packaging/linux"

PACKAGE_NAME="${PACKAGE_NAME:-tasktimer-link-b24}"
TARGET_ARCH=amd64
MAINTAINER="${PACKAGE_MAINTAINER:-alexandrgert <alexandrgert@gmail.com>}"
VENV="${VENV:-$PROJECT_DIR/.venv}"
PYTHON="${PYTHON:-$VENV/bin/python}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/tasktimer-link-b24}"
BIN_NAME="${BIN_NAME:-tasktimer-link-b24}"
BUMP="${BUMP:-patch}"
DIST_DIR="$PROJECT_DIR/dist"

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

if [[ -z "${VERSION:-}" && "${NO_BUMP:-0}" != "1" ]]; then
  echo "==> Semver bump (${BUMP}) в pyproject.toml"
  "$PYTHON" "$PROJECT_DIR/scripts/bump_version.py" "$BUMP" >/dev/null
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

echo "==> Установка зависимостей сборки"
"$PYTHON" -m pip install -q -e "$PROJECT_DIR" -r "$PROJECT_DIR/requirements-build.txt"

deb_file="${PACKAGE_NAME}-${VERSION}-${TARGET_ARCH}.deb"
deb_out="${DIST_DIR}/${deb_file}"
package_title="${PACKAGE_TITLE:-TaskTimer link B24}"

echo "==> Сборка ${deb_file}"

echo "==> PyInstaller (TaskTimer-linux.spec)"
cd "$PROJECT_DIR"
"$PYTHON" -m PyInstaller --noconfirm --clean TaskTimer-linux.spec

if [[ ! -x "$DIST_DIR/TaskTimer/TaskTimer" ]]; then
  echo "Не найден бинарник: $DIST_DIR/TaskTimer/TaskTimer" >&2
  exit 1
fi

build_root="$(mktemp -d)"
opt_rel="${INSTALL_PREFIX#/}"
install_dir="$build_root/$opt_rel"

mkdir -p "$install_dir"
cp -a "$DIST_DIR/TaskTimer/." "$install_dir/"
echo "$VERSION" > "$install_dir/VERSION"

mkdir -p "$build_root/usr/bin"
cat > "$build_root/usr/bin/$BIN_NAME" <<EOF
#!/bin/sh
exec ${INSTALL_PREFIX}/TaskTimer "\$@"
EOF
chmod 755 "$build_root/usr/bin/$BIN_NAME"

mkdir -p "$build_root/usr/share/applications"
cat > "$build_root/usr/share/applications/tasktimer-link-b24.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${package_title}
Name[ru]=${package_title}
Comment=Desktop task timer with Bitrix24 integration
Comment[ru]=Таймер задач с интеграцией Битрикс24
Exec=${BIN_NAME}
Icon=tasktimer-link-b24
Terminal=false
Categories=Office;Utility;
StartupWMClass=tasktimer-link-b24
EOF

mkdir -p "$build_root/usr/share/icons/hicolor/scalable/apps"
cp "$PACKAGING_DIR/tasktimer.svg" "$build_root/usr/share/icons/hicolor/scalable/apps/tasktimer-link-b24.svg"

installed_size_kb="$(
  du -sk "$build_root/$opt_rel" "$build_root/usr" 2>/dev/null | awk '{s += $1} END {print s}'
)"

mkdir -p "$build_root/DEBIAN"
cat > "$build_root/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${TARGET_ARCH}
Installed-Size: ${installed_size_kb}
Maintainer: ${MAINTAINER}
Conflicts: tasktimer
Replaces: tasktimer
Depends: libc6 (>= 2.31), libglib2.0-0, libx11-6, libxcb1, libxkbcommon0, libdbus-1-3, libfontconfig1, libfreetype6, libgl1, libegl1, libxext6, libxrender1, libxi6, libxrandr2, libxss1, libxcursor1, libxinerama1, libtiff5 | libtiff6
Description: ${package_title}
 Desktop task timer: daily plan, focus mode, Bitrix24 tasks and smart-process projects.
EOF

cat > "$build_root/DEBIAN/preinst" <<EOF
#!/bin/sh
set -e
PKG_NAME="${PACKAGE_NAME}"
NEW_VERSION="${VERSION}"
is_installed() { dpkg-query -W -f='\${Status}' "\$PKG_NAME" 2>/dev/null | grep -q "install ok installed"; }
installed_version() { dpkg-query -W -f='\${Version}' "\$PKG_NAME" 2>/dev/null; }
reject_downgrade() {
  old_version="\$1"
  if [ -z "\$old_version" ]; then return 0; fi
  if dpkg --compare-versions "\$NEW_VERSION" lt "\$old_version"; then
    echo "Ошибка: уже установлена более новая версия \$PKG_NAME (\$old_version)." >&2
    exit 1
  fi
}
case "\$1" in
  install) is_installed && reject_downgrade "\$(installed_version)" ;;
  upgrade) reject_downgrade "\$2" ;;
esac
exit 0
EOF
chmod 755 "$build_root/DEBIAN/preinst"

cat > "$build_root/DEBIAN/postinst" <<EOF
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$build_root/DEBIAN/postinst"

cat > "$build_root/DEBIAN/postrm" <<'EOF'
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
chmod 755 "$build_root/DEBIAN/postrm"

mkdir -p "$DIST_DIR"
rm -f "$deb_out"
dpkg-deb --build --root-owner-group "$build_root" "$deb_out"
rm -rf "$build_root"

echo "Готово: $deb_out"
ls -lh "$deb_out"
dpkg-deb -I "$deb_out" | grep -E '^( Package| Version| Architecture| Installed-Size| Maintainer):'
