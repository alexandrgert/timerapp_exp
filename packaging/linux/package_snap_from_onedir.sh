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
command -v snap >/dev/null
command -v unsquashfs >/dev/null || {
  echo "Error: unsquashfs required for snap acceptance check; install squashfs-tools." >&2
  exit 1
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
prime_dir="$work/prime"

mkdir -p "$prime_dir/bin" "$prime_dir/lib/timerapp-exp" "$prime_dir/meta/gui"
cp -a "$ONEDIR/." "$prime_dir/lib/timerapp-exp/"
cat > "$prime_dir/bin/timerapp-exp" <<'EOF'
#!/bin/sh
exec "$SNAP/lib/timerapp-exp/TaskTimer" "$@"
EOF
chmod 755 "$prime_dir/bin/timerapp-exp"
cp "$PROJECT_DIR/packaging/linux/tasktimer.svg" "$prime_dir/timerapp-exp.svg"
cp "$PROJECT_DIR/packaging/linux/timerapp-exp.desktop" \
  "$prime_dir/meta/gui/timerapp-exp.desktop"

cat > "$prime_dir/meta/snap.yaml" <<EOF
name: timerapp-exp
base: core22
version: '${VERSION}'
summary: TaskTimer Experiment
description: |
  Experimental desktop task timer with Bitrix24 integration.
grade: devel
confinement: strict
architectures: [amd64]

apps:
  timerapp-exp:
    command: bin/timerapp-exp
    plugs: [network, desktop, desktop-legacy, wayland, x11, opengl, home, gsettings]
    desktop: meta/gui/timerapp-exp.desktop
    common-id: com.timerapp.exp
EOF

# Keep ${SNAP} literal: the desktop launcher expands it when the snap runs.
sed -i 's|^Exec=.*|Exec=timerapp-exp|' "$prime_dir/meta/gui/timerapp-exp.desktop"
sed -i 's|^Icon=.*|Icon=\${SNAP}/timerapp-exp.svg|' \
  "$prime_dir/meta/gui/timerapp-exp.desktop"

mkdir -p "$DIST_DIR"
snap pack "$prime_dir" "$DIST_DIR" --filename="$(basename "$OUT")"

echo "Готово: $OUT"
ls -lh "$OUT"
unsquashfs -l "$OUT" >/dev/null
mapfile -t _snap_listing < <(unsquashfs -l "$OUT")
printf '%s\n' "${_snap_listing[@]:0:40}"
