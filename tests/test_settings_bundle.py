"""Tests for settings export/import bundle."""
from __future__ import annotations

from pathlib import Path

from timerapp_ag.app_prefs import AppPrefs
from timerapp_ag.bitrix_config import BitrixPortalConfig
from timerapp_ag.settings_bundle import (
    SETTINGS_BUNDLE_FORMAT,
    SettingsExportPayload,
    apply_settings_import,
    build_settings_bundle,
    export_settings_to_path,
    load_settings_bundle_from_path,
    parse_settings_bundle,
)
from timerapp_ag.webdav_config import WebDavConfig, load_webdav_config, save_webdav_config


def test_build_and_parse_round_trip() -> None:
    payload = SettingsExportPayload(
        reminder_interval_minutes=42,
        bitrix_webhook="https://portal.example/rest/1/token/",
        bitrix_portal=BitrixPortalConfig(projects_entity_type_id=150),
        webdav=WebDavConfig(
            enabled=True,
            url="https://cloud.example/dav/",
            username="user",
            password="secret",
        ),
        app=AppPrefs(check_updates=True, update_check_interval_days=3),
    )
    bundle = build_settings_bundle(payload)
    assert bundle["format"] == SETTINGS_BUNDLE_FORMAT
    parsed = parse_settings_bundle(bundle)
    assert parsed.ok is True
    assert parsed.reminder_interval_minutes == 42
    assert parsed.bitrix_webhook == "https://portal.example/rest/1/token/"
    assert parsed.webdav is not None
    assert parsed.webdav.password == "secret"
    assert parsed.app is not None
    assert parsed.app.update_check_interval_days == 3


def test_export_import_file_preserves_local_device_id(tmp_path: Path, monkeypatch) -> None:
    webdav_path = tmp_path / "webdav.json"
    bitrix_path = tmp_path / "bitrix.json"
    app_path = tmp_path / "app.json"
    monkeypatch.setattr("timerapp_ag.platform_paths.webdav_config_path", lambda: webdav_path)
    monkeypatch.setattr("timerapp_ag.platform_paths.bitrix_secrets_path", lambda: bitrix_path)
    monkeypatch.setattr("timerapp_ag.app_prefs.app_prefs_path", lambda: app_path)
    monkeypatch.setattr("timerapp_ag.webdav_config.webdav_config_path", lambda: webdav_path)
    monkeypatch.setattr("timerapp_ag.bitrix_secrets.platform_paths.bitrix_secrets_path", lambda: bitrix_path)

    save_webdav_config(
        WebDavConfig(
            enabled=False,
            url="https://old.example/",
            username="old",
            password="oldpass",
            device_id="local-device-1",
            last_remote_content_hash="abc",
        )
    )

    export_path = tmp_path / "settings.json"
    export_settings_to_path(
        export_path,
        SettingsExportPayload(
            reminder_interval_minutes=30,
            bitrix_webhook="https://hook.example/",
            bitrix_portal=BitrixPortalConfig(),
            webdav=WebDavConfig(
                enabled=True,
                url="https://new.example/",
                username="new",
                password="newpass",
                device_id="other-device",
            ),
            app=AppPrefs(check_updates=True),
        ),
    )
    parsed = load_settings_bundle_from_path(export_path)
    assert parsed.ok is True
    applied = apply_settings_import(parsed, preserve_local_device_id=True)
    assert applied.ok is True
    loaded = load_webdav_config()
    assert loaded.url == "https://new.example/"
    assert loaded.password == "newpass"
    assert loaded.device_id == "local-device-1"
    mode = export_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_export_preserves_worklog_portal_fields() -> None:
    portal = BitrixPortalConfig(
        projects_entity_type_id=150,
        worklog_entity_type_id=999,
        worklog_parent_field="UF_CRM_CUSTOM_PARENT",
        worklog_hours_field="UF_CRM_CUSTOM_HOURS",
    )
    payload = SettingsExportPayload(
        reminder_interval_minutes=30,
        bitrix_webhook="",
        bitrix_portal=portal,
        webdav=WebDavConfig(),
        app=AppPrefs(),
    )
    parsed = parse_settings_bundle(build_settings_bundle(payload))
    assert parsed.ok is True
    assert parsed.bitrix_portal is not None
    assert parsed.bitrix_portal.worklog_entity_type_id == 999
    assert parsed.bitrix_portal.worklog_parent_field == "UF_CRM_CUSTOM_PARENT"
    assert parsed.bitrix_portal.worklog_hours_field == "UF_CRM_CUSTOM_HOURS"


def test_import_requires_double_confirm_helper_messages() -> None:
    # pure parse rejection
    bad = parse_settings_bundle({"format": "other", "version": 1})
    assert bad.ok is False
    assert "формат" in bad.error.lower() or "Неизвестный" in bad.error
