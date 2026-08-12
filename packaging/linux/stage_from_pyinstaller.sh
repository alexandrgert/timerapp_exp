#!/usr/bin/env bash
# packaging/linux/stage_from_pyinstaller.sh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
STAGING_DIR="${STAGING_DIR:?STAGING_DIR required}"
VERSION="${VERSION:?VERSION required}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/timerapp_exp}"
BIN_NAME="${BIN_NAME:-timerapp-exp}"
PACKAGE_TITLE="${PACKAGE_TITLE:-TaskTimer Experiment}"
PACKAGING_DIR="${PACKAGING_DIR:-$PROJECT_DIR/packaging/linux}"

if [[ ! -x "$ONEDIR/TaskTimer" ]]; then
  echo "Missing onedir binary: $ONEDIR/TaskTimer" >&2
  exit 1
fi

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
opt_rel="${INSTALL_PREFIX#/}"
install_dir="$STAGING_DIR/$opt_rel"
mkdir -p "$install_dir"
cp -a "$ONEDIR/." "$install_dir/"
echo "$VERSION" > "$install_dir/VERSION"

mkdir -p "$STAGING_DIR/usr/bin"
cat > "$STAGING_DIR/usr/bin/$BIN_NAME" <<EOF
#!/bin/sh
exec ${INSTALL_PREFIX}/TaskTimer "\$@"
EOF
chmod 755 "$STAGING_DIR/usr/bin/$BIN_NAME"

mkdir -p "$STAGING_DIR/usr/share/applications"
cat > "$STAGING_DIR/usr/share/applications/timerapp-exp.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${PACKAGE_TITLE}
Name[ru]=${PACKAGE_TITLE}
Comment=Experimental desktop task timer with Bitrix24 integration
Comment[ru]=Экспериментальный таймер задач с интеграцией Битрикс24
Exec=${BIN_NAME}
Icon=timerapp-exp
Terminal=false
Categories=Office;Utility;
StartupWMClass=timerapp-exp
EOF

mkdir -p "$STAGING_DIR/usr/share/icons/hicolor/scalable/apps"
cp "$PACKAGING_DIR/tasktimer.svg" \
  "$STAGING_DIR/usr/share/icons/hicolor/scalable/apps/timerapp-exp.svg"

echo "Staged into $STAGING_DIR"
