from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

from timerapp_ag.legacy_merge import (
    find_legacy_merge_preview,
    load_declined_fingerprint,
    mark_legacy_merge_declined,
    sources_fingerprint,
)
from timerapp_ag.legacy_merge_ui import _confirm_and_merge
from timerapp_ag.storage import Storage, discover_data_files, discover_legacy_data_files


def _write_tasks(path: Path, task_id: str, title: str, *, extra_session: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sessions = [
        {
            "id": "s1",
            "started_at": "2026-06-15T10:00:00",
            "ended_at": "2026-06-15T11:00:00",
        },
    ]
    if extra_session:
        sessions.append(
            {
                "id": "s2",
                "started_at": "2026-06-15T12:00:00",
                "ended_at": None,
            },
        )
    path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": task_id,
                        "day": "2026-06-15",
                        "title": title,
                        "status": "open",
                        "sessions": sessions,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )


def _preview(tmp_path: Path, monkeypatch) -> object:
    share_root = tmp_path / "share" / "timerapp"
    primary = share_root / "TaskTimer link B24" / "data.json"
    legacy = share_root / "TaskTimer" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(legacy, "t1", "Старая")
    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: None)
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge._legacy_merge_config_path",
        lambda: tmp_path / "legacy-merge.json",
    )
    preview = find_legacy_merge_preview(primary)
    assert preview is not None
    return preview


def _mock_merge_dialog(monkeypatch, answer: QMessageBox.StandardButton) -> None:
    class FakeMessageBox:
        StandardButton = QMessageBox.StandardButton

        def __init__(self, parent=None) -> None:
            self._answer = answer

        def setWindowTitle(self, title: str) -> None:
            return None

        def setText(self, text: str) -> None:
            return None

        def setDetailedText(self, text: str) -> None:
            return None

        def setStandardButtons(self, buttons) -> None:
            return None

        def setDefaultButton(self, button) -> None:
            return None

        def exec(self) -> QMessageBox.StandardButton:
            return self._answer

        @staticmethod
        def information(*args, **kwargs) -> None:
            return None

    monkeypatch.setattr("timerapp_ag.legacy_merge_ui.QMessageBox", FakeMessageBox)


def test_confirm_merge_startup_no_records_decline(tmp_path: Path, monkeypatch) -> None:
    preview = _preview(tmp_path, monkeypatch)
    storage = Storage(path=preview.primary_path, migrate_legacy=False)
    _mock_merge_dialog(monkeypatch, QMessageBox.StandardButton.No)

    assert (
        _confirm_and_merge(
            None,
            "Test",
            storage,
            preview,
            record_decline_on_cancel=True,
        )
        is False
    )
    assert load_declined_fingerprint() == sources_fingerprint(preview.source_paths)


def test_confirm_merge_manual_no_does_not_record_decline(tmp_path: Path, monkeypatch) -> None:
    preview = _preview(tmp_path, monkeypatch)
    storage = Storage(path=preview.primary_path, migrate_legacy=False)
    _mock_merge_dialog(monkeypatch, QMessageBox.StandardButton.No)

    assert (
        _confirm_and_merge(
            None,
            "Test",
            storage,
            preview,
            record_decline_on_cancel=False,
        )
        is False
    )
    assert load_declined_fingerprint() == ""


def test_confirm_merge_yes_clears_decline_and_merges(tmp_path: Path, monkeypatch) -> None:
    preview = _preview(tmp_path, monkeypatch)
    storage = Storage(path=preview.primary_path, migrate_legacy=False)
    mark_legacy_merge_declined(preview)
    _mock_merge_dialog(monkeypatch, QMessageBox.StandardButton.Yes)

    assert _confirm_and_merge(
        None,
        "Test",
        storage,
        preview,
        record_decline_on_cancel=True,
    )
    assert load_declined_fingerprint() == ""
    assert len(storage.load().tasks) == 2


def test_find_legacy_merge_preview_reports_enriched_tasks(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / "timerapp"
    primary = share_root / "TaskTimer link B24" / "data.json"
    legacy = share_root / "TaskTimer link B24 0.2.2" / "data.json"
    _write_tasks(primary, "t0", "Общая", extra_session=False)
    _write_tasks(legacy, "t0", "Общая", extra_session=True)

    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: None)

    preview = find_legacy_merge_preview(primary)

    assert preview is not None
    assert preview.current_tasks == preview.merged_tasks == 1
    assert preview.new_titles == []
    assert "Общая" in preview.enriched_titles


def test_discover_legacy_data_files_ignores_qt_path(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / "timerapp"
    stable = share_root / "TaskTimer link B24" / "data.json"
    stable.parent.mkdir(parents=True)
    stable.write_text('{"tasks": []}', encoding="utf-8")
    qt_path = tmp_path / "qt" / "data.json"
    qt_path.parent.mkdir(parents=True)
    qt_path.write_text('{"tasks": [{"id": "qt", "day": "2026-06-15", "title": "Qt"}]}', encoding="utf-8")

    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: qt_path.resolve())

    assert qt_path.resolve() in {p.resolve() for p in discover_data_files()}
    assert qt_path.resolve() not in {p.resolve() for p in discover_legacy_data_files()}
