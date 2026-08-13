#!/usr/bin/env bash
# packaging/linux/package_snap_from_onedir.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONEDIR="${ONEDIR:-$PROJECT_DIR/dist/TaskTimer}"
VERSION="${VERSION:?VERSION required}"
DIST_DIR="${DIST_DIR:-$PROJECT_DIR/dist}"
OUT="${DIST_DIR}/timerapp-exp-${VERSION}-amd64.snap"

require_x86_64_host() {
  case "$(uname -m)" in
    x86_64) ;;
    *)
      echo "Error: Snap packaging requires an x86_64 (amd64) host; got $(uname -m)." >&2
      exit 1
      ;;
  esac
}

if [[ -n "${ARCH:-}" && "${ARCH}" != "amd64" && "${ARCH}" != "x86_64" ]]; then
  echo "Unsupported ARCH=${ARCH}; expected amd64 or x86_64." >&2
  exit 1
fi

require_x86_64_host

[[ -x "$ONEDIR/TaskTimer" ]] || { echo "Missing onedir" >&2; exit 1; }
command -v snapcraft >/dev/null

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/prime-src/bin" "$work/prime-src/lib/timerapp-exp"
cp -a "$ONEDIR/." "$work/prime-src/lib/timerapp-exp/"
cat > "$work/prime-src/bin/timerapp-exp" <<'EOF'
#!/bin/sh
exec "$SNAP/lib/timerapp-exp/TaskTimer" "$@"
EOF
chmod 755 "$work/prime-src/bin/timerapp-exp"
cp "$PROJECT_DIR/packaging/linux/tasktimer.svg" "$work/prime-src/timerapp-exp.svg"
cp "$PROJECT_DIR/packaging/linux/timerapp-exp.desktop" "$work/prime-src/timerapp-exp.desktop"

cat > "$work/snapcraft.yaml" <<EOF
name: timerapp-exp
base: core22
version: '${VERSION}'
summary: TaskTimer Experiment
description: |
  Experimental desktop task timer with Bitrix24 integration.
grade: devel
confinement: strict

apps:
  timerapp-exp:
    command: bin/timerapp-exp
    plugs: [network, desktop, desktop-legacy, wayland, x11, opengl, home, gsettings]
    desktop: timerapp-exp.desktop
    common-id: com.timerapp.exp

parts:
  app:
    plugin: dump
    source: ./prime-src
    stage-packages: []
EOF

# Keep ${SNAP} literal: the desktop launcher expands it when the snap runs.
sed -i 's|^Exec=.*|Exec=timerapp-exp|' "$work/prime-src/timerapp-exp.desktop"
sed -i 's|^Icon=.*|Icon=${SNAP}/timerapp-exp.svg|' "$work/prime-src/timerapp-exp.desktop"

mkdir -p "$DIST_DIR"
(
  cd "$work"
  snapcraft pack --destructive-mode -o "$OUT" || snapcraft pack --destructive-mode
)

# If snapcraft wrote its default name, normalize it.
if [[ ! -f "$OUT" ]]; then
  built="$(find "$work" -maxdepth 2 -name 'timerapp-exp_*.snap' | head -n1)"
  [[ -n "$built" ]] || { echo "snapcraft produced no .snap" >&2; exit 1; }
  cp -f "$built" "$OUT"
fi

echo "Готово: $OUT"
ls -lh "$OUT"
unsquashfs -l "$OUT" | head -n 40
