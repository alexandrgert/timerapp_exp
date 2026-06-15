"""Загрузка переменных окружения для standalone-репозитория."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .platform_paths import user_env_path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(dotenv_path: Optional[Path] = None, override: bool = False) -> None:
        path = Path(dotenv_path) if dotenv_path else Path(".env")
        if not path.is_file():
            return
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if override or key not in os.environ:
                os.environ[key] = value


def find_project_root() -> Path:
    """Корень репозитория (рядом с pyproject.toml)."""
    raw = os.environ.get("TASKTIMER_ROOT", "").strip()
    if raw:
        candidate = Path(raw).expanduser().resolve()
        if _is_project_root(candidate):
            return candidate
    here = Path(__file__).resolve()
    for parent in here.parents:
        if _is_project_root(parent):
            return parent
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if _is_project_root(parent):
            return parent
    return cwd


def _is_project_root(path: Path) -> bool:
    return path.is_dir() and (path / "pyproject.toml").is_file()


def load_env() -> None:
    """
    Порядок (последующие слои перекрывают предыдущие):

    1. `<repo>/.env` (override=False)
    2. пользовательский конфиг (~/.config/tasktimer/.env или %APPDATA%\\TaskTimer\\.env)
    """
    root = find_project_root()
    root_env = root / ".env"
    if root_env.is_file():
        load_dotenv(root_env, override=False)

    user_env = user_env_path()
    if user_env.is_file():
        load_dotenv(user_env, override=True)
