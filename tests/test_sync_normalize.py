from __future__ import annotations

from datetime import datetime

from timerapp_ag.domain.state import AppState
from timerapp_ag.domain.sync_normalize import normalize_running_tasks
from timerapp_ag.models import Session, Task, TaskStatus, make_id


def _running_task(task_id: str, started: str) -> Task:
    return Task(
        id=task_id,
        day="2026-06-15",
        title=task_id,
        status=TaskStatus.RUNNING,
        sessions=[Session(id=make_id(), started_at=started)],
    )


def test_normalize_running_tasks_keeps_latest() -> None:
    state = AppState(
        tasks=[
            _running_task("a", "2026-06-15T10:00:00"),
            _running_task("b", "2026-06-15T12:00:00"),
        ]
    )
    now = datetime(2026, 6, 15, 13, 0, 0)

    assert normalize_running_tasks(state, now=now) is True

    running = [task for task in state.tasks if task.status == TaskStatus.RUNNING]
    assert len(running) == 1
    assert running[0].id == "b"
    paused = next(task for task in state.tasks if task.id == "a")
    assert paused.status == TaskStatus.PAUSED
    assert paused.active_session() is None


def test_normalize_running_tasks_noop_for_single() -> None:
    state = AppState(tasks=[_running_task("only", "2026-06-15T10:00:00")])
    assert normalize_running_tasks(state) is False
