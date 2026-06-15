"""Безопасная запись локальных JSON-файлов с секретами."""
from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _harden_path(path: Path) -> None:
    """Права 0600 на файл; каталог конфигурации — 0700 (best effort)."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        logger.warning("Не удалось установить chmod 0600 для %s: %s", path, exc)
    parent = path.parent
    if not parent.is_dir():
        return
    try:
        mode = parent.stat().st_mode & 0o777
        if mode != 0o700:
            parent.chmod(stat.S_IRWXU)
    except OSError as exc:
        logger.warning("Не удалось установить chmod 0700 для %s: %s", parent, exc)


def write_json_secrets(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(stat.S_IRWXU)
    except OSError:
        pass
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)
    _harden_path(path)
