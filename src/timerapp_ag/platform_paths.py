"""Кросс-платформенные пути данных и конфигурации (desktop: Win / macOS / Linux)."""
from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path

from .app_info import APP_TITLE_BASE, STORAGE_ORG


class Platform(Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    ANDROID = "android"
    IOS = "ios"


def detect_platform() -> Platform:
    if sys.platform == "win32":
        return Platform.WINDOWS
    if sys.platform == "darwin":
        return Platform.MACOS
    return Platform.LINUX


def config_dir() -> Path:
    """Секреты и .env: bitrix.json, webdav.json, .env."""
    platform = detect_platform()
    if platform is Platform.WINDOWS:
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "TaskTimer"
        return Path.home() / "AppData" / "Roaming" / "TaskTimer"
    if platform is Platform.MACOS:
        return Path.home() / "Library" / "Application Support" / "TaskTimer"
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg) / "tasktimer"
    return Path.home() / ".config" / "tasktimer"


def _local_data_home() -> Path:
    platform = detect_platform()
    if platform is Platform.WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            return Path(local)
        return Path.home() / "AppData" / "Local"
    if platform is Platform.MACOS:
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


def data_share_roots() -> list[Path]:
    """Корни для поиска legacy data.json (все версии приложения)."""
    roots: list[Path] = []
    primary = _local_data_home() / STORAGE_ORG
    roots.append(primary)
    if detect_platform() is Platform.LINUX:
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        if xdg:
            candidate = Path(xdg) / STORAGE_ORG
            if candidate.resolve() not in {item.resolve() for item in roots}:
                roots.append(candidate)
        fallback = Path.home() / ".local" / "share" / STORAGE_ORG
        if fallback.resolve() not in {item.resolve() for item in roots}:
            roots.append(fallback)
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def stable_data_dir() -> Path:
    """Каталог основной базы: <data_root>/<org>/<APP_TITLE_BASE>/."""
    for root in data_share_roots():
        target = root / APP_TITLE_BASE
        try:
            target.mkdir(parents=True, exist_ok=True)
            test_file = target / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return target.resolve()
        except OSError:
            continue
    target = Path.cwd() / ".localdata"
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def stable_data_path() -> Path:
    return stable_data_dir() / "data.json"


def bitrix_secrets_path() -> Path:
    return config_dir() / "bitrix.json"


def webdav_config_path() -> Path:
    return config_dir() / "webdav.json"


def user_env_path() -> Path:
    return config_dir() / ".env"
