from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from ..models import Session, Task, TaskStatus
from .priority import merge_daily_priorities
from .datetime_util import duration_seconds, parse_iso_datetime
from .state import AppState


def _session_total_seconds(task: Task) -> int:
    return sum(session.duration_seconds() for session in task.sessions)


def _pick_richer_session(existing: Session, candidate: Session) -> Session:
    if existing.ended_at and not candidate.ended_at:
        return existing
    if candidate.ended_at and not existing.ended_at:
        return candidate
    existing_seconds = duration_seconds(existing.started_at, existing.ended_at)
    candidate_seconds = duration_seconds(candidate.started_at, candidate.ended_at)
    if candidate_seconds != existing_seconds:
        return candidate if candidate_seconds > existing_seconds else existing
    return candidate


def _latest_completed_at(*values: str | None) -> str | None:
    present = [value for value in values if value]
    if not present:
        return None
    return max(present, key=parse_iso_datetime)


def _resolve_merged_status(
    left: Task,
    right: Task,
    sessions: list[Session],
) -> tuple[TaskStatus, str | None]:
    if any(session.ended_at is None for session in sessions):
        return TaskStatus.RUNNING, None
    if left.is_completed() or right.is_completed():
        return TaskStatus.COMPLETED, _latest_completed_at(left.completed_at, right.completed_at)
    if sessions:
        return TaskStatus.PAUSED, None
    base = right if task_richer(right, left) else left
    return base.status, None


def merge_task_pair(left: Task, right: Task) -> Task:
    """Объединить две копии одной задачи: union sessions по id, метаданные — от более полной."""
    if left.id != right.id:
        raise ValueError(f"Task id mismatch: {left.id!r} vs {right.id!r}")
    sessions_by_id: dict[str, Session] = {}
    for session in left.sessions + right.sessions:
        existing = sessions_by_id.get(session.id)
        if existing is None:
            sessions_by_id[session.id] = session
        else:
            sessions_by_id[session.id] = _pick_richer_session(existing, session)
    merged_sessions = sorted(sessions_by_id.values(), key=lambda item: item.started_at)
    base = right if task_richer(right, left) else left
    other = left if base is right else right
    planned_days = list(dict.fromkeys((base.planned_days or []) + (other.planned_days or [])))
    daily_priorities = merge_daily_priorities(base.daily_priorities, other.daily_priorities)
    description = base.description or other.description
    status, completed_at = _resolve_merged_status(left, right, merged_sessions)
    return replace(
        base,
        sessions=merged_sessions,
        planned_days=planned_days,
        daily_priorities=daily_priorities,
        description=description,
        status=status,
        completed_at=completed_at,
    )


def task_richer(candidate: Task, current: Task) -> bool:
    if len(candidate.sessions) != len(current.sessions):
        return len(candidate.sessions) > len(current.sessions)
    cand_seconds = _session_total_seconds(candidate)
    curr_seconds = _session_total_seconds(current)
    if cand_seconds != curr_seconds:
        return cand_seconds > curr_seconds
    return candidate.created_at >= current.created_at


def score_data_file(path: Path) -> tuple[int, int, float]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (0, 0, 0.0)
    tasks = payload.get("tasks")
    task_count = len(tasks) if isinstance(tasks, list) else 0
    stat = path.stat()
    return (task_count, stat.st_size, stat.st_mtime)


def pick_best_data_file(candidates: list[Path]) -> Path | None:
    if not candidates:
        return None
    return max(candidates, key=score_data_file)


def merge_states(states: list[AppState]) -> AppState:
    """Объединить несколько состояний: задачи по id с union sessions, ui из «самого полного» файла."""
    if not states:
        return AppState()
    ranked = sorted(
        states,
        key=lambda state: (len(state.tasks), sum(len(task.sessions) for task in state.tasks)),
        reverse=True,
    )
    merged_ui = dict(ranked[0].ui)
    tasks_by_id: dict[str, Task] = {}
    for state in states:
        for task in state.tasks:
            existing = tasks_by_id.get(task.id)
            if existing is None:
                tasks_by_id[task.id] = task
            else:
                tasks_by_id[task.id] = merge_task_pair(existing, task)
    return AppState(tasks=list(tasks_by_id.values()), ui=merged_ui)


def _sessions_equivalent(left_sessions: list, right_sessions: list) -> bool:
    if len(left_sessions) != len(right_sessions):
        return False
    left_sorted = sorted(left_sessions, key=lambda session: session.id)
    right_sorted = sorted(right_sessions, key=lambda session: session.id)
    for left_session, right_session in zip(left_sorted, right_sorted, strict=True):
        if left_session.id != right_session.id:
            return False
        if left_session.started_at != right_session.started_at:
            return False
        if left_session.ended_at != right_session.ended_at:
            return False
    return True


def states_equivalent(left: AppState, right: AppState) -> bool:
    if len(left.tasks) != len(right.tasks):
        return False
    left_tasks = sorted(left.tasks, key=lambda task: task.id)
    right_tasks = sorted(right.tasks, key=lambda task: task.id)
    for left_task, right_task in zip(left_tasks, right_tasks, strict=True):
        if left_task.id != right_task.id:
            return False
        if left_task.title != right_task.title:
            return False
        if not _sessions_equivalent(left_task.sessions, right_task.sessions):
            return False
    return left.ui == right.ui
