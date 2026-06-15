from __future__ import annotations

import json
from pathlib import Path

from ..models import Task
from .state import AppState


def task_richer(candidate: Task, current: Task) -> bool:
    if len(candidate.sessions) != len(current.sessions):
        return len(candidate.sessions) > len(current.sessions)
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
    """Объединить несколько состояний: задачи по id, ui из «самого полного» файла."""
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
            if existing is None or task_richer(task, existing):
                tasks_by_id[task.id] = task
    return AppState(tasks=list(tasks_by_id.values()), ui=merged_ui)


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
        if len(left_task.sessions) != len(right_task.sessions):
            return False
    return left.ui == right.ui
