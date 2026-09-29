#!/usr/bin/env bash
# Run inside Dockerfile.compat, on an explicitly approved CI build.
set -euo pipefail
cd "$(dirname "$0")/../.."
test "$(getconf GNU_LIBC_VERSION)" = 'glibc 2.31'
# Named TZ values need the system zoneinfo database, not just a TZ variable.
TZ=Europe/Moscow python3.12 - <<'PY_TZ'
from datetime import datetime
actual = datetime.fromisoformat("2026-06-28T20:31:00+03:00").astimezone().strftime("%H:%M %z")
assert actual == "20:31 +0300", f"Missing or invalid system tzdata: Europe/Moscow resolved to {actual}"
print("System tzdata: Europe/Moscow OK")
PY_TZ
python3.12 -m venv /tmp/tasktimer-build-venv
export VENV=/tmp/tasktimer-build-venv
export PYTHON="$VENV/bin/python"
"$PYTHON" -m pip install --no-cache-dir -e . -r requirements-build.txt -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen "$PYTHON" -m pytest -q tests
"$PYTHON" -m unittest discover -s packaging/linux/tests -v
export VERSION
VERSION="$("$PYTHON" -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
ALLOW_NO_BUMP=1 NO_BUMP=1 OFFLINE=1 bash build_deb.sh
