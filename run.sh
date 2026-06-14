#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
VENV="$PROJECT_DIR/.venv"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Сначала создайте venv в каталоге проекта:"
  echo "  python -m venv .venv"
  echo "  .venv/bin/pip install -e . -r requirements-dev.txt"
  exit 1
fi

export TASKTIMER_ROOT="$PROJECT_DIR"
exec "$VENV/bin/python" app.py
