from __future__ import annotations

from datetime import date, datetime, time, timedelta

from ..models import Session, Task, TaskStatus, make_id
from .constants import SCHEMA_VERSION
from .queries import active_task, find_task, today_str
from .state import AppState


CONTINUATION_SUFFIX = " (продолжение)"


def strip_continuation_suffix(title: str) -> str:
    while title.endswith(CONTINUATION_SUFFIX):
        title = title[: -len(CONTINUATION_SUFFIX)]
    return title


def collapse_continuations(state: AppState) -> None:
    """Merge old '(продолжение)' chains into their root task."""
    by_id = {task.id: task for task in state.tasks}

    def root_of(task: Task) -> Task:
        seen: set[str] = set()
        while task.continuation_of and task.continuation_of in by_id and task.id not in seen:
            seen.add(task.id)
            task = by_id[task.continuation_of]
        return task

    chains: dict[str, list[Task]] = {}
    for task in state.tasks:
        chains.setdefault(root_of(task).id, []).append(task)

    survivors: list[Task] = []
    for root_id, members in chains.items():
        root = by_id[root_id]
        members.sort(key=lambda item: item.day)
        for member in members:
            if member.id != root.id:
                root.sessions.extend(member.sessions)
        latest = members[-1]
        root.status = latest.status
        root.completed_at = latest.completed_at if latest.is_completed() else None
        root.title = strip_continuation_suffix(root.title)
        root.sessions.sort(key=lambda item: item.started_at)
        root.planned_days = sorted({member.day for member in members} | set(root.planned_days or []))
        survivors.append(root)
    state.tasks = survivors


def migrate_schema_v2(state: AppState, *, today: str | None = None) -> bool:
    """Migrate to persistent-task + plan model. Returns True if state changed."""
    if int(state.ui.get("schema_version", 1)) >= SCHEMA_VERSION:
        return False
    collapse_continuations(state)
    for task in state.tasks:
        if not task.planned_days:
            task.planned_days = [task.day]
    state.ui["schema_version"] = SCHEMA_VERSION
    state.ui["plan_rollover_day"] = today or today_str()
    return True


def close_cross_day_active_task(state: AppState, today: str) -> bool:
    """Stop a running session that started on a previous calendar day."""
    active = active_task(state)
    if active is None:
        return False
    session = active.active_session()
    if session is None:
        return False
    if session.start_dt.date().isoformat() == today:
        return False
    previous_day = session.start_dt.date()
    session.ended_at = datetime.combine(previous_day, time(23, 59, 59)).isoformat()
    active.status = TaskStatus.PAUSED
    return True


def ensure_plan_rollover(state: AppState, *, today: str | None = None) -> bool:
    """Carry yesterday's unfinished plan into today. Returns True if state changed."""
    today = today or today_str()
    close_cross_day_active_task(state, today)
    if state.ui.get("plan_rollover_day") == today:
        return False
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    for task in state.tasks:
        if task.is_completed():
            continue
        if yesterday in (task.planned_days or []) and today not in task.planned_days:
            task.planned_days.append(today)
    state.ui["plan_rollover_day"] = today
    return True


def add_to_plan(state: AppState, task_id: str, today: str) -> bool:
    task = find_task(state, task_id)
    if today in task.planned_days:
        return False
    task.planned_days.append(today)
    return True


def remove_from_plan(state: AppState, task_id: str, today: str) -> bool:
    task = find_task(state, task_id)
    changed = False
    if today in task.planned_days:
        task.planned_days = [day for day in task.planned_days if day != today]
        changed = True
    if today in task.daily_priorities:
        del task.daily_priorities[today]
        changed = True
    return changed
