#!/usr/bin/env bash
# packaging/linux/package_tarballs_from_staging.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="${STAGING_DIR:?STAGING_DIR required}"
VERSION="${VERSION:?VERSION required}"
PACKAGE_NAME="${PACKAGE_NAME:-timerapp-exp}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"

if [[ ! -d "$STAGING_DIR" ]]; then
  echo "Missing staging directory: $STAGING_DIR" >&2
  exit 1
fi

# write INSTALL.txt into staging copy:
#   Install: sudo tar -C / -xvf timerapp-exp-…-linux-amd64.tar.xz --exclude=INSTALL.txt
#   or extract then sudo cp -a opt usr /
#   Remove: sudo rm -rf /opt/timerapp_exp /usr/bin/timerapp-exp …
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -a "$STAGING_DIR/." "$work/"
cat > "$work/INSTALL.txt" <<'EOF'
TaskTimer Experiment — portable tree
Install (as root): tar -C / -xvf THIS_ARCHIVE --exclude=INSTALL.txt
Remove: rm -rf /opt/timerapp_exp /usr/bin/timerapp-exp \
  /usr/share/applications/timerapp-exp.desktop \
  /usr/share/icons/hicolor/scalable/apps/timerapp-exp.svg
EOF
base="${PACKAGE_NAME}-${VERSION}-linux-amd64"
mkdir -p "$DIST_DIR"
tar -C "$work" -cJf "${DIST_DIR}/${base}.tar.xz" .
tar -C "$work" -czf "${DIST_DIR}/${base}.tgz" .

echo "Готово: ${DIST_DIR}/${base}.tar.xz"
echo "Готово: ${DIST_DIR}/${base}.tgz"
ls -lh "${DIST_DIR}/${base}.tar.xz" "${DIST_DIR}/${base}.tgz"
