"""Нормализация состояния после merge / sync."""
from __future__ import annotations

from datetime import datetime

from ..models import Task, TaskStatus
from .state import AppState


def _latest_running_start(task: Task) -> datetime:
    session = task.active_session()
    if session is None:
        return datetime.min
    return session.start_dt


def normalize_running_tasks(state: AppState, *, now: datetime | None = None) -> bool:
    """Оставить не более одной running-задачи; остальные — paused."""
    now = now or datetime.now()
    running = [
        task
        for task in state.tasks
        if task.status == TaskStatus.RUNNING and task.active_session()
    ]
    if len(running) <= 1:
        return False

    winner = max(running, key=_latest_running_start)
    changed = False
    for task in running:
        if task.id == winner.id:
            continue
        session = task.active_session()
        if session is not None and session.ended_at is None:
            session.ended_at = now.isoformat()
            changed = True
        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.PAUSED
            changed = True
    return changed
