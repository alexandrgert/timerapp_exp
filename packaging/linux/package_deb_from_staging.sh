#!/usr/bin/env bash
# packaging/linux/package_deb_from_staging.sh
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

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "Установите dpkg-deb: sudo apt install dpkg" >&2
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -a "$STAGING_DIR/." "$work/"

installed_size_kb="$(
  du -sk "$work" 2>/dev/null | awk '{print $1}'
)"

mkdir -p "$work/DEBIAN"
cat > "$work/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${TARGET_ARCH}
Installed-Size: ${installed_size_kb}
Maintainer: ${MAINTAINER}
Depends: libc6 (>= 2.31), libglib2.0-0, libx11-6, libxcb1, libxkbcommon0, libdbus-1-3, libfontconfig1, libfreetype6, libgl1, libegl1, libxext6, libxrender1, libxi6, libxrandr2, libxss1, libxcursor1, libxinerama1, libtiff5 | libtiff6
Description: ${PACKAGE_TITLE}
 Experimental desktop task timer: daily plan, focus mode, Bitrix24 tasks and smart-process projects.
EOF

cat > "$work/DEBIAN/preinst" <<EOF
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
chmod 755 "$work/DEBIAN/preinst"

cat > "$work/DEBIAN/postinst" <<EOF
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
chmod 755 "$work/DEBIAN/postinst"

cat > "$work/DEBIAN/postrm" <<'EOF'
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
chmod 755 "$work/DEBIAN/postrm"

deb_file="${PACKAGE_NAME}-${VERSION}-${TARGET_ARCH}.deb"
deb_out="${DIST_DIR}/${deb_file}"
mkdir -p "$DIST_DIR"
rm -f "$deb_out"
dpkg-deb --build --root-owner-group "$work" "$deb_out"

echo "Готово: $deb_out"
ls -lh "$deb_out"
dpkg-deb -I "$deb_out" | grep -E '^( Package| Version| Architecture| Installed-Size| Maintainer):'
