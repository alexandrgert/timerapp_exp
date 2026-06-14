from __future__ import annotations

from pathlib import Path

from timerapp_ag.models import Session, Task, TaskStatus
from timerapp_ag.storage import AppState, Storage


def test_load_missing_file_returns_empty_state(tmp_path: Path) -> None:
    storage = Storage(path=tmp_path / "missing.json")
    state = storage.load()
    assert state.tasks == []
    assert state.ui["reminder_interval_minutes"] == 40


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    storage = Storage(path=tmp_path / "data.json")
    state = AppState(
        tasks=[
            Task(
                id="t1",
                day="2026-01-01",
                title="Demo",
                status=TaskStatus.PAUSED,
                sessions=[Session(id="s", started_at="2026-01-01T10:00:00", ended_at="2026-01-01T10:10:00")],
            )
        ]
    )
    state.ui["reminder_interval_minutes"] = 25
    storage.save(state)

    reloaded = storage.load()
    assert len(reloaded.tasks) == 1
    assert reloaded.tasks[0].title == "Demo"
    assert reloaded.tasks[0].status == TaskStatus.PAUSED
    assert reloaded.ui["reminder_interval_minutes"] == 25


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    storage = Storage(path=tmp_path / "nested" / "deep" / "data.json")
    storage.save(AppState())
    assert (tmp_path / "nested" / "deep" / "data.json").exists()


def test_from_dict_backfills_missing_ui_keys() -> None:
    state = AppState.from_dict({"tasks": [], "ui": {}})
    assert state.ui["filter_open_only"] is False
    assert state.ui["reminder_interval_minutes"] == 40
    assert state.ui["focus_timer"]["selected_minutes"] == 20


def test_saved_json_is_human_readable_utf8(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    storage = Storage(path=path)
    storage.save(AppState(tasks=[Task(id="t1", day="2026-01-01", title="Задача")]))
    text = path.read_text(encoding="utf-8")
    assert "Задача" in text  # ensure_ascii=False keeps cyrillic legible
