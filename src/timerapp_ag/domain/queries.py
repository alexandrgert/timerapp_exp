from __future__ import annotations

from datetime import date, datetime

from ..models import Task, TaskStatus
from .priority import filter_tasks_by_priority, sort_key_by_priority
from .datetime_util import local_now, session_local_date
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


def timer_panel_task(state: AppState) -> Task | None:
    """Side timer: running task, or the most recently paused one with sessions."""
    running = active_task(state)
    if running is not None:
        return running
    paused = [
        task
        for task in state.tasks
        if task.status == TaskStatus.PAUSED and task.sessions
    ]
    if not paused:
        return None
    return max(paused, key=_last_pause_dt)


def _last_pause_dt(task: Task) -> datetime:
    session = task.sessions[-1]
    return session.end_dt or session.start_dt


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


def tasks_today_plan(
    state: AppState,
    today: str,
    *,
    priority_levels: set[int] | None = None,
) -> list[Task]:
    today_tasks = [
        task
        for task in state.tasks
        if today in (task.planned_days or []) and _show_in_today_plan(task, today)
    ]
    if priority_levels is not None:
        running_ids = {task.id for task in running_tasks(state)}
        today_tasks = _filter_tasks_by_priority_preserving(
            today_tasks,
            today,
            priority_levels,
            preserve_ids=running_ids,
        )
    active = active_task(state)

    def sort_key(task: Task) -> tuple[int, int, int, str]:
        if active is not None and task.id == active.id:
            return (0, 0, 0, "")
        completed = 1 if task.is_completed() else 0
        return (1, completed, sort_key_by_priority(task, today), task.created_at)

    return sorted(today_tasks, key=sort_key)


def _show_in_today_plan(task: Task, today: str) -> bool:
    if task.day == today:
        return True
    if task.status == TaskStatus.RUNNING and task.active_session() is not None:
        return True
    return today in (task.daily_priorities or {})


def visible_on_today_plan(task: Task, today: str) -> bool:
    return today in (task.planned_days or []) and _show_in_today_plan(task, today)


def _filter_tasks_by_priority_preserving(
    tasks: list[Task],
    today: str,
    levels: set[int],
    *,
    preserve_ids: set[str],
) -> list[Task]:
    filtered = filter_tasks_by_priority(tasks, today, levels)
    if not preserve_ids:
        return filtered
    kept_ids = {task.id for task in filtered}
    restored = list(filtered)
    for task in tasks:
        if task.id in preserve_ids and task.id not in kept_ids:
            restored.append(task)
    return restored


def tasks_on_date(state: AppState, date_iso: str, *, now: datetime | None = None) -> list[Task]:
    now = now or datetime.now()
    return view_sorted(
        state,
        [task for task in state.tasks if today_seconds(task, date_iso, now=now) > 0],
    )


def in_today_plan(task: Task, today: str) -> bool:
    return today in (task.planned_days or [])


def today_seconds(task: Task, today: str, *, now: datetime | None = None) -> int:
    now = now or local_now()
    return sum(
        session.duration_seconds(now=now)
        for session in task.sessions
        if session_local_date(session.started_at) == today
    )


def today_total_seconds(state: AppState, today: str, *, now: datetime | None = None) -> int:
    now = now or local_now()
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
