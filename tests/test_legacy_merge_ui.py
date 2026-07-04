from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

from timerapp_ag.app_info import APP_TITLE_BASE, STORAGE_ORG
from timerapp_ag.legacy_merge import (
    add_configured_legacy_location,
    find_legacy_merge_preview,
    list_configured_legacy_locations,
    load_declined_fingerprint,
    mark_legacy_merge_declined,
    sources_fingerprint,
)
from timerapp_ag.storage import Storage, discover_data_files, discover_legacy_data_files

from timerapp_ag.legacy_merge_ui import (
    _confirm_and_merge,
    _remove_configured_legacy_location,
    configure_legacy_data_location,
    manage_legacy_data_locations,
    offer_legacy_merge_manual,
)


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
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
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
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
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
    share_root = tmp_path / "share" / STORAGE_ORG
    stable = share_root / APP_TITLE_BASE / "data.json"
    stable.parent.mkdir(parents=True)
    stable.write_text('{"tasks": []}', encoding="utf-8")
    qt_path = tmp_path / "qt" / "data.json"
    qt_path.parent.mkdir(parents=True)
    qt_path.write_text('{"tasks": [{"id": "qt", "day": "2026-06-15", "title": "Qt"}]}', encoding="utf-8")

    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: qt_path.resolve())

    assert qt_path.resolve() in {p.resolve() for p in discover_data_files()}
    assert qt_path.resolve() not in {p.resolve() for p in discover_legacy_data_files()}


def _seed_legacy_location(tmp_path: Path, monkeypatch, location: Path) -> None:
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge._legacy_merge_config_path",
        lambda: tmp_path / "legacy-merge.json",
    )
    data_file = location / "data.json"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text('{"tasks": []}', encoding="utf-8")
    add_configured_legacy_location(location)


class _ManageLocationsMessageBox:
    ButtonRole = QMessageBox.ButtonRole

    def __init__(self, parent=None, *, click_label: str = "Закрыть") -> None:
        self._click_label = click_label
        self._buttons: dict[str, MagicMock] = {}
        self._chosen: MagicMock | None = None

    def setWindowTitle(self, title: str) -> None:
        return None

    def setText(self, text: str) -> None:
        return None

    def addButton(self, label: str, role) -> MagicMock:
        button = MagicMock()
        button.label = label
        self._buttons[label] = button
        return button

    def setDefaultButton(self, button) -> None:
        return None

    def exec(self) -> int:
        self._chosen = self._buttons[self._click_label]
        return 0

    def clickedButton(self):
        return self._chosen

    @staticmethod
    def information(*args, **kwargs) -> None:
        return None


def _patch_manage_locations_dialog(monkeypatch, click_label: str) -> None:
    class PatchedMessageBox(_ManageLocationsMessageBox):
        ButtonRole = QMessageBox.ButtonRole

        def __init__(self, parent=None) -> None:
            super().__init__(parent, click_label=click_label)

    PatchedMessageBox.information = staticmethod(lambda *args, **kwargs: None)
    monkeypatch.setattr("timerapp_ag.legacy_merge_ui.QMessageBox", PatchedMessageBox)


def test_manage_legacy_data_locations_close_keeps_paths(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    location = tmp_path / "legacy-a"
    _seed_legacy_location(tmp_path, monkeypatch, location)

    _patch_manage_locations_dialog(monkeypatch, "Закрыть")
    monkeypatch.setattr("timerapp_ag.legacy_merge_ui.configure_legacy_data_location", MagicMock())
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui._remove_configured_legacy_location",
        MagicMock(),
    )

    manage_legacy_data_locations(None, "Test")

    assert location.as_posix() in list_configured_legacy_locations()


def test_manage_legacy_data_locations_remove_deletes_path(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    location = tmp_path / "legacy-a"
    _seed_legacy_location(tmp_path, monkeypatch, location)

    _patch_manage_locations_dialog(monkeypatch, "Удалить каталог…")

    manage_legacy_data_locations(None, "Test")

    assert list_configured_legacy_locations() == []


def test_manage_legacy_data_locations_add_opens_picker(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    location = tmp_path / "legacy-a"
    _seed_legacy_location(tmp_path, monkeypatch, location)

    _patch_manage_locations_dialog(monkeypatch, "Добавить каталог…")
    configure = MagicMock(return_value=False)
    monkeypatch.setattr("timerapp_ag.legacy_merge_ui.configure_legacy_data_location", configure)

    manage_legacy_data_locations(None, "Test")

    configure.assert_called_once_with(None, "Test")
    assert location.as_posix() in list_configured_legacy_locations()


def test_configure_legacy_data_location_uses_local_data_home(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    data_home = tmp_path / "appdata-local"
    data_home.mkdir()
    legacy_file = tmp_path / "legacy" / "data.json"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text('{"tasks": []}', encoding="utf-8")

    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.platform_paths._local_data_home",
        lambda: data_home,
    )
    captured: list[str] = []

    def fake_open_file(parent, title, start_dir, file_filter) -> tuple[str, str]:
        captured.append(start_dir)
        return str(legacy_file), "JSON (*.json)"

    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QFileDialog.getOpenFileName",
        fake_open_file,
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QMessageBox.information",
        staticmethod(lambda *args, **kwargs: None),
    )

    assert configure_legacy_data_location(None, "Test") is True
    assert captured == [str(data_home)]
    assert legacy_file.parent.as_posix() in list_configured_legacy_locations()


def test_configure_legacy_data_location_picks_directory_when_file_cancelled(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    legacy_dir = tmp_path / "TaskTimer link B24"
    legacy_dir.mkdir()
    (legacy_dir / "data.json").write_text('{"tasks": []}', encoding="utf-8")

    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.platform_paths._local_data_home",
        lambda: tmp_path / "share",
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: ("", ""),
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(legacy_dir),
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QMessageBox.information",
        staticmethod(lambda *args, **kwargs: None),
    )

    assert configure_legacy_data_location(None, "Test") is True
    assert legacy_dir.as_posix() in list_configured_legacy_locations()


def test_configure_legacy_data_location_invalid_path_shows_warning(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    missing = tmp_path / "missing-dir"

    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.platform_paths._local_data_home",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(missing), ""),
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QMessageBox.warning",
        staticmethod(lambda parent, title, text: warnings.append(text)),
    )

    assert configure_legacy_data_location(None, "Test") is False
    assert warnings
    assert "data.json" in warnings[0]


def test_configure_legacy_data_location_cancelled_returns_false(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.platform_paths._local_data_home",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: ("", ""),
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: "",
    )

    assert configure_legacy_data_location(None, "Test") is False


def test_manage_legacy_data_locations_empty_opens_configure(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    configure = MagicMock(return_value=True)
    informed: list[str] = []

    monkeypatch.setattr("timerapp_ag.legacy_merge_ui.configure_legacy_data_location", configure)
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QMessageBox.information",
        staticmethod(lambda parent, title, text: informed.append(text)),
    )

    manage_legacy_data_locations(None, "Test")

    configure.assert_called_once_with(None, "Test")
    assert informed
    assert "сохранён" in informed[0].lower()


def test_remove_configured_legacy_location_multiple_uses_picker(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    first = tmp_path / "legacy-a"
    second = tmp_path / "legacy-b"
    _seed_legacy_location(tmp_path, monkeypatch, first)
    add_configured_legacy_location(second)

    labels = [
        f"1. {first.as_posix()}",
        f"2. {second.as_posix()}",
    ]
    monkeypatch.setattr(
        "PySide6.QtWidgets.QInputDialog.getItem",
        lambda parent, title, label, items, current, editable: (labels[1], True),
    )
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.QMessageBox.information",
        staticmethod(lambda *args, **kwargs: None),
    )

    _remove_configured_legacy_location(None, "Test", [first.as_posix(), second.as_posix()])

    remaining = list_configured_legacy_locations()
    assert first.as_posix() in remaining
    assert second.as_posix() not in remaining


def test_offer_legacy_merge_manual_no_preview_user_declines_configure(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    primary.parent.mkdir(parents=True)
    primary.write_text('{"tasks": []}', encoding="utf-8")
    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: None)

    class QuestionBox:
        StandardButton = QMessageBox.StandardButton

        @staticmethod
        def question(parent, title, text, buttons, default):
            return QMessageBox.StandardButton.No

        @staticmethod
        def information(parent, title, text):
            QuestionBox.informed = text

    monkeypatch.setattr("timerapp_ag.legacy_merge_ui.QMessageBox", QuestionBox)
    storage = Storage(path=primary, migrate_legacy=False)

    assert offer_legacy_merge_manual(None, "Test", storage) is False
    assert "не найдено" in QuestionBox.informed.lower()


def test_offer_legacy_merge_manual_with_preview_merges(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    preview = _preview(tmp_path, monkeypatch)
    storage = Storage(path=preview.primary_path, migrate_legacy=False)
    _mock_merge_dialog(monkeypatch, QMessageBox.StandardButton.Yes)

    assert offer_legacy_merge_manual(None, "Test", storage) is True
    assert len(storage.load().tasks) == 2


def test_offer_legacy_merge_manual_configure_equivalent_shows_not_found(
    tmp_path: Path, monkeypatch, qapp
) -> None:
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    external = tmp_path / "external" / "TaskTimer link B24" / "data.json"
    _write_tasks(primary, "t0", "Same")
    _write_tasks(external, "t0", "Same")
    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: None)

    class QuestionBox:
        StandardButton = QMessageBox.StandardButton
        informed: list[str] = []

        @staticmethod
        def question(parent, title, text, buttons, default):
            return QMessageBox.StandardButton.Yes

        @staticmethod
        def information(parent, title, text):
            QuestionBox.informed.append(text)

    monkeypatch.setattr("timerapp_ag.legacy_merge_ui.QMessageBox", QuestionBox)
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge_ui.configure_legacy_data_location",
        lambda parent, title: add_configured_legacy_location(external.parent)[0] is not None,
    )
    storage = Storage(path=primary, migrate_legacy=False)

    assert offer_legacy_merge_manual(None, "Test", storage) is False
    assert external.parent.as_posix() in list_configured_legacy_locations()
    assert any("не найдено" in text.lower() for text in QuestionBox.informed)
