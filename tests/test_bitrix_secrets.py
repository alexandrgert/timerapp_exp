from __future__ import annotations

import json
from pathlib import Path

from timerapp_ag.bitrix_secrets import (
    import_webhook_from_ui,
    load_bitrix_webhook,
    save_bitrix_webhook,
    strip_bitrix_secrets_from_ui,
)
from timerapp_ag.controller import AppController
from timerapp_ag.storage import AppState, Storage


def test_bitrix_webhook_saved_locally_not_in_data_json(storage: Storage) -> None:
    controller = AppController(storage)
    url = "https://acme.bitrix24.ru/rest/1/abc/"
    controller.set_bitrix_webhook(url)

    data = json.loads(storage.path.read_text(encoding="utf-8"))
    bitrix = data.get("ui", {}).get("bitrix", {})
    assert "webhook_url" not in bitrix
    assert load_bitrix_webhook() == url


def test_legacy_webhook_migrated_from_data_json(storage: Storage, isolated_bitrix_secrets: Path) -> None:
    payload = {
        "tasks": [],
        "ui": {"bitrix": {"webhook_url": "https://acme.bitrix24.ru/rest/1/legacy/"}},
    }
    storage.path.write_text(json.dumps(payload), encoding="utf-8")

    controller = AppController(storage)
    assert controller.bitrix_webhook() == "https://acme.bitrix24.ru/rest/1/legacy/"

    data = json.loads(storage.path.read_text(encoding="utf-8"))
    assert "webhook_url" not in data.get("ui", {}).get("bitrix", {})


def test_import_webhook_prefers_existing_local_secret(isolated_bitrix_secrets: Path) -> None:
    save_bitrix_webhook("https://acme.bitrix24.ru/rest/1/local/")
    ui = {"bitrix": {"webhook_url": "https://acme.bitrix24.ru/rest/1/remote/"}}
    assert import_webhook_from_ui(ui) is True
    assert load_bitrix_webhook() == "https://acme.bitrix24.ru/rest/1/local/"
    assert "webhook_url" not in ui["bitrix"]


def test_storage_save_strips_webhook_from_payload(storage: Storage) -> None:
    state = AppState()
    state.ui["bitrix"] = {
        "webhook_url": "https://acme.bitrix24.ru/rest/1/secret/",
        "portal": {"projects_entity_type_id": 150},
    }
    storage.save(state)
    data = json.loads(storage.path.read_text(encoding="utf-8"))
    bitrix = data["ui"]["bitrix"]
    assert "webhook_url" not in bitrix
    assert bitrix["portal"]["projects_entity_type_id"] == 150


def test_strip_bitrix_secrets_from_ui_noop_when_missing() -> None:
    ui: dict = {"bitrix": {"portal": {}}}
    assert strip_bitrix_secrets_from_ui(ui) is False
