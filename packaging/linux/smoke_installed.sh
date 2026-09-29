#!/usr/bin/env bash
# Run as root only in disposable Ubuntu containers. Never on a user's desktop.
# Usage: bash packaging/linux/smoke_installed.sh path/to/package.deb
set -euo pipefail
package=$(realpath "${1:?DEB path required}")
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends "$package" xvfb xauth dbus-x11
useradd --create-home --shell /bin/bash tasktimer-smoke
log=$(mktemp)
trap 'rm -f "$log"' EXIT
status=0
runuser -u tasktimer-smoke -- env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 \
    timeout 45s xvfb-run -a dbus-run-session -- \
    timerapp-exp --startup-smoke-test >"$log" 2>&1 || status=$?
cat "$log"
if [ "$status" -ne 0 ] || ! grep -qx 'TASKTIMER_STARTUP_OK' "$log"; then
    # Fresh disposable user: these logs cannot contain real user settings.
    find /home/tasktimer-smoke/.local/state/timerapp-exp -name 'launch.*.log' -type f -exec cat {} \; || true
    echo "Installed package failed startup acceptance (exit $status)" >&2
    exit 1
fi
echo 'Installed package: main window and Qt event loop passed'
