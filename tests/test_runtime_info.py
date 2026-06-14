from __future__ import annotations

from pathlib import Path

from timerapp_ag.runtime_info import bitrix_webhook_configured, build_about_report


def test_bitrix_webhook_configured_from_stored() -> None:
    assert bitrix_webhook_configured(stored_webhook="https://p.bitrix24.ru/rest/1/secret/") is True


def test_bitrix_webhook_configured_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BITRIX24_HOOK_URL", "https://p.bitrix24.ru/rest/1/secret/")
    assert bitrix_webhook_configured(stored_webhook="") is True


def test_bitrix_webhook_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("BITRIX24_HOOK_URL", raising=False)
    assert bitrix_webhook_configured(stored_webhook="") is False


def test_build_about_report_contains_sections(monkeypatch) -> None:
    monkeypatch.delenv("BITRIX24_HOOK_URL", raising=False)
    report = build_about_report(stored_webhook="", data_path=Path("/tmp/data.json"))

    assert "Версия" in report
    assert "Система" in report
    assert "Среда выполнения" in report
    assert "Данные и конфигурация" in report
    assert "Каталог установки:" in report
    assert "Файл данных: /tmp/data.json" in report
    assert "Вебхук Битрикс24: не настроен" in report


def test_build_about_report_masks_webhook_presence(monkeypatch) -> None:
    monkeypatch.setenv("BITRIX24_HOOK_URL", "https://p.bitrix24.ru/rest/1/top-secret/")
    report = build_about_report(stored_webhook="")

    assert "top-secret" not in report
    assert "Вебхук Битрикс24: настроен" in report


def test_build_about_report_shows_dev_root_in_checkout() -> None:
    report = build_about_report(stored_webhook="")
    assert "Каталог разработки:" in report
