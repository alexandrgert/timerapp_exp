"""Название приложения и версия для окна и диалога «О программе»."""
from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

APP_TITLE_BASE = "TaskTimer link B24"
DESKTOP_FILE_NAME = "tasktimer-link-b24"


def app_install_dir() -> Path:
    """Каталог бинарника (в .deb — /opt/.../TaskTimer)."""
    return Path(sys.executable).resolve().parent


def resolve_app_version() -> str | None:
    """Версия из VERSION рядом с бинарником; None, если файла нет."""
    version_file = app_install_dir() / "VERSION"
    if not version_file.is_file():
        return None
    value = version_file.read_text(encoding="utf-8").strip()
    return value or None


def resolve_app_version_label() -> str:
    """Единая строка версии: VERSION-файл → metadata пакета → «неизвестна»."""
    file_version = resolve_app_version()
    if file_version:
        return file_version
    try:
        return version("timerapp-ag")
    except PackageNotFoundError:
        return "неизвестна"


def resolve_app_title() -> str:
    """Заголовок окна; в .deb рядом с бинарником лежит файл VERSION."""
    file_version = resolve_app_version()
    if file_version:
        return f"{APP_TITLE_BASE} {file_version}"
    return APP_TITLE_BASE
