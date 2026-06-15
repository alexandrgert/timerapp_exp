"""Локальные секреты Битрикс24 (не попадают в синхронизируемый data.json)."""
from __future__ import annotations

import json
from typing import Any

from . import platform_paths
from .secure_files import write_json_secrets


def strip_bitrix_secrets_from_ui(ui: dict[str, Any]) -> bool:
    """Remove webhook_url from ui.bitrix before persisting or syncing."""
    bitrix = ui.get("bitrix")
    if not isinstance(bitrix, dict):
        return False
    if "webhook_url" not in bitrix:
        return False
    bitrix.pop("webhook_url", None)
    return True


def load_bitrix_webhook() -> str:
    path = platform_paths.bitrix_secrets_path()
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("webhook_url") or "").strip()


def save_bitrix_webhook(url: str) -> None:
    write_json_secrets(
        platform_paths.bitrix_secrets_path(),
        {"webhook_url": (url or "").strip()},
    )


def import_webhook_from_ui(ui: dict[str, Any]) -> bool:
    """Move legacy webhook_url from data.json ui into the local secrets file."""
    bitrix = ui.get("bitrix")
    if not isinstance(bitrix, dict):
        return False
    legacy = str(bitrix.get("webhook_url") or "").strip()
    if not legacy:
        return False
    if not load_bitrix_webhook():
        save_bitrix_webhook(legacy)
    bitrix.pop("webhook_url", None)
    return True
