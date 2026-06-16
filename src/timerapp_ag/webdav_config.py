"""Локальные настройки WebDAV (не попадают в синхронизируемый data.json)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

from . import platform_paths
from .secure_files import write_json_secrets
from .webdav_meta import META_SUFFIX

DEFAULT_REMOTE_PATH = "tasktimer/data.json"


@dataclass
class WebDavConfig:
    enabled: bool = False
    url: str = ""
    username: str = ""
    password: str = ""
    remote_path: str = DEFAULT_REMOTE_PATH
    sync_on_startup: bool = True
    sync_on_shutdown: bool = True
    shutdown_upload_only: bool = False
    last_sync_at: str | None = None
    last_error: str = ""
    device_id: str = ""
    last_remote_content_hash: str = ""
    last_sync_had_conflict: bool = False
    pending_notice: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "url": self.url,
            "username": self.username,
            "password": self.password,
            "remote_path": self.remote_path,
            "sync_on_startup": self.sync_on_startup,
            "sync_on_shutdown": self.sync_on_shutdown,
            "shutdown_upload_only": self.shutdown_upload_only,
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
            "device_id": self.device_id,
            "last_remote_content_hash": self.last_remote_content_hash,
            "last_sync_had_conflict": self.last_sync_had_conflict,
            "pending_notice": self.pending_notice,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WebDavConfig:
        if not isinstance(data, dict):
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            url=str(data.get("url", "") or "").strip(),
            username=str(data.get("username", "") or "").strip(),
            password=str(data.get("password", "") or ""),
            remote_path=str(data.get("remote_path") or DEFAULT_REMOTE_PATH).strip() or DEFAULT_REMOTE_PATH,
            sync_on_startup=bool(data.get("sync_on_startup", True)),
            sync_on_shutdown=bool(data.get("sync_on_shutdown", True)),
            shutdown_upload_only=bool(data.get("shutdown_upload_only", False)),
            last_sync_at=data.get("last_sync_at"),
            last_error=str(data.get("last_error", "") or ""),
            device_id=str(data.get("device_id") or "").strip(),
            last_remote_content_hash=str(data.get("last_remote_content_hash") or "").strip(),
            last_sync_had_conflict=bool(data.get("last_sync_had_conflict", False)),
            pending_notice=str(data.get("pending_notice") or "").strip(),
        )

    def is_configured(self) -> bool:
        return bool(self.url.strip() and self.username.strip())

    def remote_url(self) -> str:
        base = self.url.strip()
        if not base.endswith("/"):
            base += "/"
        path = self.remote_path.strip().lstrip("/")
        return urljoin(base, path)

    def meta_remote_url(self) -> str:
        data_url = self.remote_url()
        if data_url.endswith(".json"):
            return data_url[: -len(".json")] + META_SUFFIX
        return data_url.rstrip("/") + META_SUFFIX

    def ensure_device_id(self) -> str:
        if not self.device_id:
            self.device_id = uuid4().hex
        return self.device_id


def webdav_config_path():
    return platform_paths.webdav_config_path()


def apply_env_defaults(config: WebDavConfig) -> WebDavConfig:
    """Подставить WEBDAV_* из окружения, если поля пустые."""
    url = (os.environ.get("WEBDAV_URL") or "").strip()
    username = (os.environ.get("WEBDAV_USERNAME") or os.environ.get("WEBDAV_USER") or "").strip()
    password = os.environ.get("WEBDAV_PASSWORD") or ""
    remote_path = (os.environ.get("WEBDAV_REMOTE_PATH") or "").strip()
    enabled_env = (os.environ.get("WEBDAV_ENABLED") or "").strip().lower()

    return WebDavConfig(
        enabled=config.enabled or enabled_env in {"1", "true", "yes", "on"},
        url=config.url or url,
        username=config.username or username,
        password=config.password or password,
        remote_path=config.remote_path if config.remote_path != DEFAULT_REMOTE_PATH else (remote_path or DEFAULT_REMOTE_PATH),
        sync_on_startup=config.sync_on_startup,
        sync_on_shutdown=config.sync_on_shutdown,
        shutdown_upload_only=config.shutdown_upload_only,
        last_sync_at=config.last_sync_at,
        last_error=config.last_error,
        device_id=config.device_id,
        last_remote_content_hash=config.last_remote_content_hash,
        last_sync_had_conflict=config.last_sync_had_conflict,
        pending_notice=config.pending_notice,
    )


def load_webdav_config() -> WebDavConfig:
    path = platform_paths.webdav_config_path()
    if not path.is_file():
        config = apply_env_defaults(WebDavConfig())
        config.ensure_device_id()
        return config
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = apply_env_defaults(WebDavConfig())
        config.ensure_device_id()
        return config
    config = apply_env_defaults(WebDavConfig.from_dict(payload))
    config.ensure_device_id()
    return config


def save_webdav_config(config: WebDavConfig) -> None:
    config.ensure_device_id()
    write_json_secrets(platform_paths.webdav_config_path(), config.to_dict())


def mark_webdav_sync_ok(config: WebDavConfig, *, remote_hash: str = "", had_conflict: bool = False) -> WebDavConfig:
    updated = WebDavConfig.from_dict(config.to_dict())
    updated.last_sync_at = datetime.now().isoformat(timespec="seconds")
    updated.last_error = ""
    updated.last_sync_had_conflict = had_conflict
    if remote_hash:
        updated.last_remote_content_hash = remote_hash
    save_webdav_config(updated)
    return updated


def mark_webdav_sync_error(config: WebDavConfig, message: str) -> WebDavConfig:
    updated = WebDavConfig.from_dict(config.to_dict())
    updated.last_error = message.strip()
    save_webdav_config(updated)
    return updated


def save_webdav_pending_notice(message: str) -> None:
    config = load_webdav_config()
    updated = WebDavConfig.from_dict(config.to_dict())
    updated.pending_notice = message.strip()
    save_webdav_config(updated)


def consume_webdav_pending_notice() -> str:
    config = load_webdav_config()
    notice = (config.pending_notice or "").strip()
    if not notice:
        return ""
    updated = WebDavConfig.from_dict(config.to_dict())
    updated.pending_notice = ""
    save_webdav_config(updated)
    return notice
