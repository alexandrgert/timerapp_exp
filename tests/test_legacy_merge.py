from __future__ import annotations

import json
from pathlib import Path

from timerapp_ag.app_info import APP_TITLE_BASE, STORAGE_ORG
from timerapp_ag.legacy_merge import (
    find_legacy_merge_preview,
    format_legacy_merge_details,
    format_legacy_merge_summary,
    load_declined_fingerprint,
    mark_legacy_merge_declined,
    should_prompt_on_startup,
    sources_fingerprint,
)
from timerapp_ag.storage import Storage


def _write_tasks(path: Path, task_id: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"tasks": [{"id": task_id, "day": "2026-06-15", "title": title}]}),
        encoding="utf-8",
    )


def _isolate_legacy_discovery(monkeypatch, share_root: Path) -> None:
    monkeypatch.setattr("timerapp_ag.platform_paths.data_share_roots", lambda: [share_root.resolve()])
    monkeypatch.setattr("timerapp_ag.storage._qt_data_path_if_exists", lambda: None)


def test_find_legacy_merge_preview_detects_extra_sources(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    legacy = share_root / "TaskTimer link B24 0.2.2" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(legacy, "t1", "Из 0.2.2")

    _isolate_legacy_discovery(monkeypatch, share_root)

    preview = find_legacy_merge_preview(primary)

    assert preview is not None
    assert preview.current_tasks == 1
    assert preview.merged_tasks == 2
    assert preview.new_tasks_count == 1
    assert "Из 0.2.2" in preview.new_titles
    assert "+1 новых задач" in format_legacy_merge_summary(preview)
    assert any("0.2.2" in label for label in preview.source_labels)
    assert "0.2.2" in format_legacy_merge_details(preview)


def test_find_legacy_merge_preview_none_when_equivalent(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    duplicate = share_root / "TaskTimer" / "data.json"
    payload = json.dumps({"tasks": [{"id": "t1", "day": "2026-06-15", "title": "Одна"}]})
    primary.parent.mkdir(parents=True)
    duplicate.parent.mkdir(parents=True)
    primary.write_text(payload, encoding="utf-8")
    duplicate.write_text(payload, encoding="utf-8")

    _isolate_legacy_discovery(monkeypatch, share_root)

    assert find_legacy_merge_preview(primary) is None


def test_declined_fingerprint_skips_startup_prompt(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    legacy = share_root / "TaskTimer" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(legacy, "t1", "Старая")

    _isolate_legacy_discovery(monkeypatch, share_root)

    preview = find_legacy_merge_preview(primary)
    assert preview is not None
    assert should_prompt_on_startup(preview) is True

    mark_legacy_merge_declined(preview)
    assert should_prompt_on_startup(preview) is False
    assert load_declined_fingerprint() == sources_fingerprint(preview.source_paths)


def test_consolidate_legacy_data_files_merges_on_demand(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    legacy = share_root / "TaskTimer link B24 0.2.2" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(legacy, "t1", "Из 0.2.2")

    _isolate_legacy_discovery(monkeypatch, share_root)

    storage = Storage(path=primary, migrate_legacy=False)
    assert len(storage.load().tasks) == 1

    merged = storage.consolidate_legacy_data_files()

    assert {task.title for task in merged.tasks} == {"Текущая", "Из 0.2.2"}
    assert len(json.loads(primary.read_text(encoding="utf-8"))["tasks"]) == 2


def test_find_legacy_merge_preview_reports_session_counters(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    legacy = share_root / "TaskTimer link B24 0.2.2" / "data.json"
    primary.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    primary.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "t0",
                        "day": "2026-06-15",
                        "title": "Общая",
                        "status": "open",
                        "sessions": [
                            {
                                "id": "s1",
                                "started_at": "2026-06-15T10:00:00",
                                "ended_at": "2026-06-15T11:00:00",
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    legacy.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "t0",
                        "day": "2026-06-15",
                        "title": "Общая",
                        "status": "open",
                        "sessions": [
                            {
                                "id": "s1",
                                "started_at": "2026-06-15T10:00:00",
                                "ended_at": "2026-06-15T11:00:00",
                            },
                            {
                                "id": "s2",
                                "started_at": "2026-06-15T12:00:00",
                                "ended_at": None,
                            },
                        ],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    _isolate_legacy_discovery(monkeypatch, share_root)

    preview = find_legacy_merge_preview(primary)

    assert preview is not None
    assert preview.new_tasks_count == 0
    assert preview.enriched_tasks_count == 1
    assert preview.extra_sessions_count == 1
    assert "+1 сессий" in format_legacy_merge_summary(preview)
    assert "Общая" in format_legacy_merge_details(preview)


def test_resolve_legacy_data_json_path_accepts_dir_and_file(tmp_path: Path) -> None:
    from timerapp_ag.legacy_merge import resolve_legacy_data_json_path

    data_file = tmp_path / "TaskTimer link B24" / "data.json"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("{}", encoding="utf-8")

    assert resolve_legacy_data_json_path(data_file.parent) == data_file.resolve()
    assert resolve_legacy_data_json_path(data_file) == data_file.resolve()
    assert resolve_legacy_data_json_path(tmp_path / "missing") is None


def test_extra_legacy_path_is_included_in_merge_preview(tmp_path: Path, monkeypatch) -> None:
    from timerapp_ag.legacy_merge import (
        add_configured_legacy_location,
        find_legacy_merge_preview,
        load_legacy_merge_config,
    )
    from timerapp_ag.storage import discover_legacy_data_files

    share_root = tmp_path / "share" / STORAGE_ORG
    primary = share_root / APP_TITLE_BASE / "data.json"
    external = tmp_path / "external" / "TaskTimer link B24" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(external, "t1", "Из production")

    _isolate_legacy_discovery(monkeypatch, share_root)

    assert find_legacy_merge_preview(primary) is None

    data_path, error = add_configured_legacy_location(external.parent)
    assert error == ""
    assert data_path == external.resolve()
    assert external.parent.as_posix() in load_legacy_merge_config()["extra_data_paths"]

    discovered = discover_legacy_data_files()
    assert external.resolve() in {path.resolve() for path in discovered}

    preview = find_legacy_merge_preview(primary)
    assert preview is not None
    assert preview.new_tasks_count == 1
    assert str(external.parent) in preview.source_labels
