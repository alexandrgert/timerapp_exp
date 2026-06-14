"""Сведения о версии, системе и среде выполнения для диалога «О программе»."""
from __future__ import annotations

import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .app_info import app_install_dir, resolve_app_version_label
from .env_loader import find_project_root, user_config_env_path


def _qt_versions() -> tuple[str, str]:
    try:
        from PySide6.QtCore import qVersion

        return qVersion(), version("PySide6")
    except (ImportError, PackageNotFoundError):
        return "—", "—"


def _env_file_label(path: Path | None) -> str:
    if path is None:
        return "недоступен"
    return "найден" if path.is_file() else "нет"


def bitrix_webhook_configured(*, stored_webhook: str = "") -> bool:
    env_url = (os.environ.get("BITRIX24_HOOK_URL") or "").strip()
    return bool((stored_webhook or "").strip() or env_url)


def build_about_report(*, stored_webhook: str = "", data_path: Path | str | None = None) -> str:
    install_dir = app_install_dir()
    dev_root = find_project_root()
    dev_mode = (dev_root / "pyproject.toml").is_file()
    root_env = dev_root / ".env" if dev_mode else None
    user_env = user_config_env_path()
    data_file = Path(data_path) if data_path is not None else None
    qt_version, pyside_version = _qt_versions()
    bitrix_status = "настроен" if bitrix_webhook_configured(stored_webhook=stored_webhook) else "не настроен"

    lines = [
        "Версия",
        f"  {resolve_app_version_label()}",
        "",
        "Система",
        f"  ОС: {platform.system()} {platform.release()}",
        f"  Сборка ОС: {platform.version()}",
        f"  Архитектура: {platform.machine()}",
        "",
        "Среда выполнения",
        f"  Python: {sys.version.split()[0]}",
        f"  Исполняемый файл: {sys.executable}",
        f"  Qt: {qt_version}",
        f"  PySide6: {pyside_version}",
        f"  Платформа Qt: {os.environ.get('QT_QPA_PLATFORM', 'по умолчанию')}",
        "",
        "Данные и конфигурация",
        f"  Каталог установки: {install_dir}",
    ]
    if data_file is not None:
        lines.append(f"  Файл данных: {data_file}")
    if dev_mode:
        lines.append(f"  Каталог разработки: {dev_root}")
        if root_env is not None:
            lines.append(f"  .env в репозитории: {_env_file_label(root_env)} ({root_env})")
    if user_env is not None:
        lines.append(f"  Пользовательский .env: {_env_file_label(user_env)} ({user_env})")
    else:
        lines.append("  Пользовательский .env: недоступен")
    lines.extend(
        [
            f"  Вебхук Битрикс24: {bitrix_status}",
            f"  TASKTIMER_ROOT: {os.environ.get('TASKTIMER_ROOT', '—')}",
        ]
    )
    return "\n".join(lines)
