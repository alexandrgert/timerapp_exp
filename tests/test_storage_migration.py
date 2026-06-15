from __future__ import annotations

import json
from pathlib import Path

from timerapp_ag.storage import Storage, merge_data_files, pick_best_data_file, stable_data_path


def test_pick_best_data_file_prefers_more_tasks(tmp_path: Path) -> None:
    small = tmp_path / "small.json"
    large = tmp_path / "large.json"
    small.write_text(json.dumps({"tasks": [{"id": "1", "day": "2026-01-01", "title": "A"}]}), encoding="utf-8")
    large.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "1", "day": "2026-01-01", "title": "A"},
                    {"id": "2", "day": "2026-01-01", "title": "B"},
                    {"id": "3", "day": "2026-01-01", "title": "C"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert pick_best_data_file([small, large]) == large


def test_merge_data_files_combines_unique_tasks(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps({"tasks": [{"id": "t1", "day": "2026-06-15", "title": "Первая"}]}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"tasks": [{"id": "t2", "day": "2026-06-15", "title": "Вторая"}]}),
        encoding="utf-8",
    )

    merged = merge_data_files([first, second])

    assert {task.id for task in merged.tasks} == {"t1", "t2"}


def test_storage_merges_legacy_files_into_primary(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / "timerapp"
    legacy = share_root / "TaskTimer link B24 0.2.2" / "data.json"
    other = share_root / "TaskTimer" / "data.json"
    target = share_root / "TaskTimer link B24" / "data.json"
    legacy.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"tasks": [{"id": "t1", "day": "2026-06-15", "title": "Из 0.2.2"}]}),
        encoding="utf-8",
    )
    other.write_text(
        json.dumps({"tasks": [{"id": "t2", "day": "2026-06-14", "title": "Из TaskTimer"}]}),
        encoding="utf-8",
    )
    target.write_text(json.dumps({"tasks": []}), encoding="utf-8")

    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: None)

    storage = Storage(path=target, migrate_legacy=False)
    state = storage.consolidate_legacy_data_files()

    assert {task.title for task in state.tasks} == {"Из 0.2.2", "Из TaskTimer"}
    reloaded = json.loads(target.read_text(encoding="utf-8"))
    assert len(reloaded["tasks"]) == 2
    assert (target.parent / "backups").is_dir()


def test_save_creates_rolling_backup(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    storage = Storage(path=path, migrate_legacy=False)
    storage.save(storage.load())
    storage.save(storage.load())

    assert (tmp_path / "data.json.bak").is_file()


def test_load_recovers_from_rolling_backup(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    backup = tmp_path / "data.json.bak"
    backup.write_text(
        json.dumps({"tasks": [{"id": "t1", "day": "2026-06-15", "title": "Восстановлено"}]}),
        encoding="utf-8",
    )
    path.write_text("{ broken json", encoding="utf-8")

    storage = Storage(path=path, migrate_legacy=False)
    state = storage.load()

    assert len(state.tasks) == 1
    assert state.tasks[0].title == "Восстановлено"
    assert json.loads(path.read_text(encoding="utf-8"))["tasks"][0]["title"] == "Восстановлено"


def test_create_backup_writes_timestamped_copy(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    storage = Storage(path=path, migrate_legacy=False)
    storage.save(storage.load())

    created = storage.create_backup("exit")

    assert created is not None
    assert created.is_file()
    assert created.parent.name == "backups"


def test_stable_data_path_uses_app_title_base(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / "timerapp"
    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    assert stable_data_path() == (share_root / "TaskTimer link B24" / "data.json").resolve()
