"""Экспорт / импорт локальных настроек (не data.json, не WebDAV-синхронизация)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .app_prefs import AppPrefs, load_app_prefs, save_app_prefs
from .bitrix_config import BitrixPortalConfig
from .bitrix_secrets import load_bitrix_webhook, save_bitrix_webhook
from .secure_files import write_json_secrets
from .webdav_config import WebDavConfig, load_webdav_config, save_webdav_config

logger = logging.getLogger(__name__)

SETTINGS_BUNDLE_FORMAT = "timerapp-settings"
SETTINGS_BUNDLE_VERSION = 1


@dataclass(frozen=True)
class SettingsExportPayload:
    reminder_interval_minutes: int
    bitrix_webhook: str
    bitrix_portal: BitrixPortalConfig
    webdav: WebDavConfig
    app: AppPrefs


@dataclass(frozen=True)
class SettingsImportResult:
    ok: bool
    error: str = ""
    reminder_interval_minutes: int | None = None
    bitrix_webhook: str | None = None
    bitrix_portal: BitrixPortalConfig | None = None
    webdav: WebDavConfig | None = None
    app: AppPrefs | None = None


def build_settings_bundle(payload: SettingsExportPayload) -> dict[str, Any]:
    return {
        "format": SETTINGS_BUNDLE_FORMAT,
        "version": SETTINGS_BUNDLE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "ui": {
            "reminder_interval_minutes": int(payload.reminder_interval_minutes),
            "bitrix": payload.bitrix_portal.to_dict(),
        },
        "bitrix": {"webhook_url": (payload.bitrix_webhook or "").strip()},
        "webdav": payload.webdav.to_dict(),
        "app": payload.app.to_dict(),
    }


def export_settings_to_path(path: Path, payload: SettingsExportPayload) -> None:
    write_json_secrets(path, build_settings_bundle(payload))


def collect_settings_from_disk(
    *,
    reminder_interval_minutes: int,
    bitrix_portal: BitrixPortalConfig,
) -> SettingsExportPayload:
    return SettingsExportPayload(
        reminder_interval_minutes=reminder_interval_minutes,
        bitrix_webhook=load_bitrix_webhook(),
        bitrix_portal=bitrix_portal,
        webdav=load_webdav_config(),
        app=load_app_prefs(),
    )


def parse_settings_bundle(data: Any) -> SettingsImportResult:
    if not isinstance(data, dict):
        return SettingsImportResult(ok=False, error="Файл настроек должен быть JSON-объектом")
    if data.get("format") != SETTINGS_BUNDLE_FORMAT:
        return SettingsImportResult(
            ok=False,
            error="Неизвестный формат файла (ожидается timerapp-settings)",
        )
    try:
        version = int(data.get("version") or 0)
    except (TypeError, ValueError):
        return SettingsImportResult(ok=False, error="Некорректная версия файла настроек")
    if version < 1 or version > SETTINGS_BUNDLE_VERSION:
        return SettingsImportResult(ok=False, error=f"Неподдерживаемая версия файла: {version}")

    ui = data.get("ui") if isinstance(data.get("ui"), dict) else {}
    reminder = ui.get("reminder_interval_minutes")
    try:
        reminder_minutes = int(reminder) if reminder is not None else None
    except (TypeError, ValueError):
        return SettingsImportResult(ok=False, error="Некорректный reminder_interval_minutes")

    portal_raw = ui.get("bitrix") if isinstance(ui.get("bitrix"), dict) else {}
    portal = BitrixPortalConfig.from_dict(portal_raw) if portal_raw else None

    bitrix = data.get("bitrix") if isinstance(data.get("bitrix"), dict) else {}
    webhook = str(bitrix.get("webhook_url") or "").strip() if bitrix else None

    webdav_raw = data.get("webdav")
    webdav = WebDavConfig.from_dict(webdav_raw) if isinstance(webdav_raw, dict) else None

    app_raw = data.get("app")
    app = AppPrefs.from_dict(app_raw) if isinstance(app_raw, dict) else None

    if webdav is None and app is None and webhook is None and reminder_minutes is None and portal is None:
        return SettingsImportResult(ok=False, error="В файле нет распознанных настроек")

    return SettingsImportResult(
        ok=True,
        reminder_interval_minutes=reminder_minutes,
        bitrix_webhook=webhook if bitrix else None,
        bitrix_portal=portal,
        webdav=webdav,
        app=app,
    )


def load_settings_bundle_from_path(path: Path) -> SettingsImportResult:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except OSError as exc:
        return SettingsImportResult(ok=False, error=f"Не удалось прочитать файл: {exc}")
    except json.JSONDecodeError as exc:
        return SettingsImportResult(ok=False, error=f"Некорректный JSON: {exc}")
    return parse_settings_bundle(data)


def apply_settings_import(
    result: SettingsImportResult,
    *,
    preserve_local_device_id: bool = True,
) -> SettingsImportResult:
    """Записать импортированные настройки на диск. Требует result.ok."""
    if not result.ok:
        return result
    try:
        if result.bitrix_webhook is not None:
            save_bitrix_webhook(result.bitrix_webhook)
        if result.app is not None:
            save_app_prefs(result.app)
        if result.webdav is not None:
            current = load_webdav_config()
            webdav = result.webdav
            if preserve_local_device_id and current.device_id:
                webdav = WebDavConfig.from_dict(
                    {
                        **webdav.to_dict(),
                        "device_id": current.device_id,
                        # runtime sync state — не тащить с другой машины
                        "last_sync_at": current.last_sync_at,
                        "last_error": "",
                        "last_remote_content_hash": current.last_remote_content_hash,
                        "last_sync_had_conflict": False,
                        "pending_notice": "",
                        "pending_remote_hash": "",
                        "pending_remote_remind_at": None,
                    }
                )
            else:
                webdav = WebDavConfig.from_dict(
                    {
                        **webdav.to_dict(),
                        "last_error": "",
                        "pending_notice": "",
                        "pending_remote_hash": "",
                        "pending_remote_remind_at": None,
                    }
                )
            save_webdav_config(webdav)
            result = SettingsImportResult(
                ok=True,
                reminder_interval_minutes=result.reminder_interval_minutes,
                bitrix_webhook=result.bitrix_webhook,
                bitrix_portal=result.bitrix_portal,
                webdav=webdav,
                app=result.app,
            )
    except OSError as exc:
        logger.error("Settings import failed: %s", exc)
        return SettingsImportResult(ok=False, error=str(exc))
    return result
