from __future__ import annotations

from datetime import date, datetime

from ..models import Task, TaskStatus
from .state import AppState


def running_tasks(state: AppState) -> list[Task]:
    return [
        task
        for task in state.tasks
        if task.status == TaskStatus.RUNNING and task.active_session()
    ]


def active_task(state: AppState) -> Task | None:
    running = running_tasks(state)
    return running[0] if running else None


def find_task(state: AppState, task_id: str) -> Task:
    for task in state.tasks:
        if task.id == task_id:
            return task
    raise KeyError(task_id)


def all_tasks(state: AppState) -> list[Task]:
    return sorted(state.tasks, key=lambda task: task.created_at, reverse=True)


def view_sorted(state: AppState, tasks: list[Task]) -> list[Task]:
    ordered = sorted(tasks, key=lambda task: task.created_at, reverse=True)
    active = active_task(state)
    if active is not None and active in ordered:
        ordered.remove(active)
        ordered.insert(0, active)
    return ordered


def tasks_all(state: AppState) -> list[Task]:
    return view_sorted(state, state.tasks)


def tasks_in_progress(state: AppState) -> list[Task]:
    return view_sorted(state, [task for task in state.tasks if not task.is_completed()])


def tasks_today_plan(state: AppState, today: str) -> list[Task]:
    return view_sorted(state, [task for task in state.tasks if today in (task.planned_days or [])])


def tasks_on_date(state: AppState, date_iso: str, *, now: datetime | None = None) -> list[Task]:
    now = now or datetime.now()
    return view_sorted(
        state,
        [task for task in state.tasks if today_seconds(task, date_iso, now=now) > 0],
    )


def in_today_plan(task: Task, today: str) -> bool:
    return today in (task.planned_days or [])


def today_seconds(task: Task, today: str, *, now: datetime | None = None) -> int:
    now = now or datetime.now()
    return sum(
        session.duration_seconds(now=now)
        for session in task.sessions
        if session.start_dt.date().isoformat() == today
    )


def today_total_seconds(state: AppState, today: str, *, now: datetime | None = None) -> int:
    now = now or datetime.now()
    return sum(today_seconds(task, today, now=now) for task in state.tasks)


def tasks_by_day(state: AppState, *, open_only: bool = False) -> list[tuple[str, list[Task]]]:
    grouped: dict[str, list[Task]] = {}
    for task in all_tasks(state):
        if open_only and task.is_completed():
            continue
        grouped.setdefault(task.day, []).append(task)
    return sorted(grouped.items(), key=lambda item: item[0], reverse=True)


def day_total_seconds(state: AppState, day: str, *, now: datetime | None = None) -> int:
    now = now or datetime.now()
    return sum(task.total_seconds(now=now) for task in state.tasks if task.day == day)


def bitrix_task_exists(state: AppState, day: str, source: object, item_id: str) -> bool:
    for task in state.tasks:
        link = task.bitrix
        if (
            task.day == day
            and isinstance(link, dict)
            and link.get("source") == source
            and str(link.get("id")) == item_id
        ):
            return True
    return False


def today_str(*, today: date | None = None) -> str:
    return (today or date.today()).isoformat()
