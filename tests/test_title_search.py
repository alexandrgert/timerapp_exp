"""Title search filter for task list (desktop)."""

from __future__ import annotations

from timerapp_ag.domain.queries import filter_tasks_by_title
from timerapp_ag.models import Task, TaskStatus


def _task(title: str, task_id: str = "t1") -> Task:
    return Task(
        id=task_id,
        day="2026-08-06",
        title=title,
        status=TaskStatus.OPEN,
        created_at="2026-08-06T10:00:00+03:00",
    )


def test_empty_needle_returns_all() -> None:
    tasks = [_task("Alpha", "a"), _task("Beta", "b")]
    assert filter_tasks_by_title(tasks, "") == tasks
    assert filter_tasks_by_title(tasks, "   ") == tasks


def test_casefold_substring_match() -> None:
    tasks = [_task("Отчёт Alpha", "a"), _task("Beta", "b")]
    assert [t.id for t in filter_tasks_by_title(tasks, "alp")] == ["a"]
    assert [t.id for t in filter_tasks_by_title(tasks, "ОТЧЁТ")] == ["a"]


def test_preserves_input_order() -> None:
    tasks = [_task("one", "1"), _task("two", "2"), _task("otone", "3")]
    assert [t.id for t in filter_tasks_by_title(tasks, "one")] == ["1", "3"]
