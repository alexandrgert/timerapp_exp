from __future__ import annotations

import json
from pathlib import Path

from timerapp_ag.legacy_merge import (
    find_legacy_merge_preview,
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
    share_root = tmp_path / "share" / "timerapp"
    primary = share_root / "TaskTimer link B24" / "data.json"
    legacy = share_root / "TaskTimer link B24 0.2.2" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(legacy, "t1", "Из 0.2.2")

    _isolate_legacy_discovery(monkeypatch, share_root)

    preview = find_legacy_merge_preview(primary)

    assert preview is not None
    assert preview.current_tasks == 1
    assert preview.merged_tasks == 2
    assert "Из 0.2.2" in preview.new_titles
    assert any("0.2.2" in label for label in preview.source_labels)


def test_find_legacy_merge_preview_none_when_equivalent(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / "timerapp"
    primary = share_root / "TaskTimer link B24" / "data.json"
    duplicate = share_root / "TaskTimer" / "data.json"
    payload = json.dumps({"tasks": [{"id": "t1", "day": "2026-06-15", "title": "Одна"}]})
    primary.parent.mkdir(parents=True)
    duplicate.parent.mkdir(parents=True)
    primary.write_text(payload, encoding="utf-8")
    duplicate.write_text(payload, encoding="utf-8")

    _isolate_legacy_discovery(monkeypatch, share_root)

    assert find_legacy_merge_preview(primary) is None


def test_declined_fingerprint_skips_startup_prompt(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / "timerapp"
    primary = share_root / "TaskTimer link B24" / "data.json"
    legacy = share_root / "TaskTimer" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(legacy, "t1", "Старая")

    _isolate_legacy_discovery(monkeypatch, share_root)
    monkeypatch.setattr(
        "timerapp_ag.legacy_merge._legacy_merge_config_path",
        lambda: tmp_path / "legacy-merge.json",
    )

    preview = find_legacy_merge_preview(primary)
    assert preview is not None
    assert should_prompt_on_startup(preview) is True

    mark_legacy_merge_declined(preview)
    assert should_prompt_on_startup(preview) is False
    assert load_declined_fingerprint() == sources_fingerprint(preview.source_paths)


def test_consolidate_legacy_data_files_merges_on_demand(tmp_path: Path, monkeypatch) -> None:
    share_root = tmp_path / "share" / "timerapp"
    primary = share_root / "TaskTimer link B24" / "data.json"
    legacy = share_root / "TaskTimer link B24 0.2.2" / "data.json"
    _write_tasks(primary, "t0", "Текущая")
    _write_tasks(legacy, "t1", "Из 0.2.2")

    _isolate_legacy_discovery(monkeypatch, share_root)

    storage = Storage(path=primary, migrate_legacy=False)
    assert len(storage.load().tasks) == 1

    merged = storage.consolidate_legacy_data_files()

    assert {task.title for task in merged.tasks} == {"Текущая", "Из 0.2.2"}
    assert len(json.loads(primary.read_text(encoding="utf-8"))["tasks"]) == 2
