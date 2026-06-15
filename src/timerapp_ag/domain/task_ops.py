from __future__ import annotations

from datetime import date, datetime, timedelta

from ..models import Session, Task, TaskStatus, make_id
from .queries import active_task, find_task, today_str
from .state import AppState


def create_task(
    state: AppState,
    title: str,
    *,
    description: str = "",
    bitrix: dict | None = None,
    day: str | None = None,
) -> Task:
    day = day or today_str()
    task = Task(
        id=make_id(),
        day=day,
        title=title.strip(),
        description=description.strip(),
        status=TaskStatus.OPEN,
        bitrix=bitrix,
        planned_days=[day],
    )
    state.tasks.append(task)
    return task


def link_bitrix(state: AppState, task_id: str, link: dict) -> None:
    find_task(state, task_id).bitrix = link


def start_task(state: AppState, task_id: str, *, now: datetime | None = None) -> Task:
    now = now or datetime.now()
    current = active_task(state)
    if current and current.id != task_id:
        stop_task(state, current.id, now=now)
    task = find_task(state, task_id)
    if task.is_completed():
        task.status = TaskStatus.OPEN
        task.completed_at = None
    if task.active_session() is None:
        task.sessions.append(Session(id=make_id(), started_at=now.isoformat()))
    task.status = TaskStatus.RUNNING
    return task


def stop_task(state: AppState, task_id: str, *, now: datetime | None = None) -> Task:
    now = now or datetime.now()
    task = find_task(state, task_id)
    session = task.active_session()
    if session and session.ended_at is None:
        session.ended_at = now.isoformat()
    if task.status != TaskStatus.COMPLETED:
        task.status = TaskStatus.PAUSED if task.sessions else TaskStatus.OPEN
    return task


def complete_task(state: AppState, task_id: str, *, now: datetime | None = None) -> Task:
    now = now or datetime.now()
    task = find_task(state, task_id)
    if task.active_session():
        stop_task(state, task_id, now=now)
    task.status = TaskStatus.COMPLETED
    task.completed_at = now.isoformat()
    return task


def resume_completed_task(state: AppState, task_id: str, *, now: datetime | None = None) -> Task:
    task = find_task(state, task_id)
    task.status = TaskStatus.OPEN
    task.completed_at = None
    return start_task(state, task_id, now=now)


def delete_task(state: AppState, task_id: str, *, now: datetime | None = None) -> None:
    now = now or datetime.now()
    task = find_task(state, task_id)
    if task.status == TaskStatus.RUNNING and task.active_session():
        stop_task(state, task_id, now=now)
    state.tasks = [item for item in state.tasks if item.id != task_id]


def add_session(
    state: AppState,
    task_id: str,
    started_at: datetime,
    ended_at: datetime,
) -> Session:
    if ended_at <= started_at:
        raise ValueError("Время окончания должно быть позже начала.")
    task = find_task(state, task_id)
    session = Session(id=make_id(), started_at=started_at.isoformat(), ended_at=ended_at.isoformat())
    task.sessions.append(session)
    task.sessions.sort(key=lambda item: item.started_at)
    return session


def delete_session(state: AppState, task_id: str, session_id: str) -> bool:
    """Returns True if a running session was removed."""
    task = find_task(state, task_id)
    removed_running = False
    for index, session in enumerate(task.sessions):
        if session.id != session_id:
            continue
        if session.ended_at is None:
            removed_running = True
        del task.sessions[index]
        break
    else:
        raise KeyError(session_id)
    if removed_running and task.status == TaskStatus.RUNNING:
        task.status = TaskStatus.PAUSED if task.sessions else TaskStatus.OPEN
    return removed_running


def update_session(
    state: AppState,
    task_id: str,
    session_id: str,
    started_at: datetime,
    ended_at: datetime,
) -> None:
    if ended_at <= started_at:
        raise ValueError("Время окончания должно быть позже начала.")
    task = find_task(state, task_id)
    for session in task.sessions:
        if session.id == session_id:
            session.started_at = started_at.isoformat()
            session.ended_at = ended_at.isoformat()
            break
    else:
        raise KeyError(session_id)
    task.sessions.sort(key=lambda item: item.started_at)


def import_bitrix_items(state: AppState, items: list[dict], *, day: str | None = None) -> tuple[int, int]:
    from .queries import bitrix_task_exists

    day = day or today_str()
    imported = skipped = 0
    for item in items:
        source = item.get("source")
        item_id = str(item.get("id"))
        if bitrix_task_exists(state, day, source, item_id):
            skipped += 1
            continue
        create_task(
            state,
            item.get("title", ""),
            bitrix={"source": source, "id": item_id},
            day=day,
        )
        imported += 1
    return imported, skipped
