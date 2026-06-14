from __future__ import annotations

from pathlib import Path

from timerapp_ag.app_info import (
    APP_TITLE_BASE,
    resolve_app_title,
    resolve_app_version,
    resolve_app_version_label,
)


def test_resolve_app_title_without_version_file(monkeypatch) -> None:
    monkeypatch.setattr("timerapp_ag.app_info.sys.executable", "/usr/bin/python3")
    assert resolve_app_title() == APP_TITLE_BASE


def test_resolve_app_title_reads_version_file(tmp_path: Path, monkeypatch) -> None:
    fake_exe = tmp_path / "TaskTimer"
    fake_exe.write_text("", encoding="utf-8")
    (tmp_path / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    monkeypatch.setattr("timerapp_ag.app_info.sys.executable", str(fake_exe))

    assert resolve_app_title() == f"{APP_TITLE_BASE} 0.2.0"
    assert resolve_app_version() == "0.2.0"
    assert resolve_app_version_label() == "0.2.0"


def test_resolve_app_version_label_falls_back_to_package(monkeypatch) -> None:
    monkeypatch.setattr("timerapp_ag.app_info.sys.executable", "/usr/bin/python3")
    label = resolve_app_version_label()
    assert label == "0.2.1" or label != "неизвестна"
