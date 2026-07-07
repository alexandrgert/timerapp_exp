from __future__ import annotations

from ..models import Task
from .state import AppState

DEFAULT_PRIORITY = 4
MIN_PRIORITY = 1
MAX_PRIORITY = 4
ALL_PRIORITIES = frozenset({1, 2, 3, 4})

PRIORITY_COLORS = {
    1: "#E74C3C",
    2: "#F1C40F",
    3: "#27AE60",
    4: "#B8BDC9",
}


def _clamp_priority(value: int) -> int:
    if value < MIN_PRIORITY or value > MAX_PRIORITY:
        raise ValueError(f"priority must be {MIN_PRIORITY}..{MAX_PRIORITY}, got {value!r}")
    return value


def clamp_priority(value: int) -> int:
    return _clamp_priority(value)


def normalize_priority(value: object) -> int:
    if not isinstance(value, int):
        return DEFAULT_PRIORITY
    if value < MIN_PRIORITY or value > MAX_PRIORITY:
        return DEFAULT_PRIORITY
    return value


def task_priority(task: Task, date_iso: str) -> int:
    raw = (task.daily_priorities or {}).get(date_iso, DEFAULT_PRIORITY)
    return normalize_priority(raw)


def sort_key_by_priority(task: Task, date_iso: str) -> int:
    return task_priority(task, date_iso)


def filter_tasks_by_priority(
    tasks: list[Task],
    date_iso: str,
    levels: set[int],
) -> list[Task]:
    if not levels:
        return list(tasks)
    return [task for task in tasks if task_priority(task, date_iso) in levels]


def _find_task(state: AppState, task_id: str) -> Task:
    for task in state.tasks:
        if task.id == task_id:
            return task
    raise KeyError(task_id)


def set_task_priority(
    state: AppState,
    task_id: str,
    date_iso: str,
    priority: int,
) -> bool:
    priority = _clamp_priority(priority)
    task = _find_task(state, task_id)
    current = task_priority(task, date_iso)
    if priority == current:
        return False
    if priority == DEFAULT_PRIORITY:
        if date_iso in task.daily_priorities:
            del task.daily_priorities[date_iso]
            return True
        return False
    task.daily_priorities[date_iso] = priority
    return True


def set_tasks_priority(
    state: AppState,
    task_ids: list[str],
    date_iso: str,
    priority: int,
) -> int:
    changed = 0
    for task_id in task_ids:
        if set_task_priority(state, task_id, date_iso, priority):
            changed += 1
    return changed


def clear_task_priority_for_day(
    state: AppState,
    task_id: str,
    date_iso: str,
) -> bool:
    task = _find_task(state, task_id)
    if date_iso not in task.daily_priorities:
        return False
    del task.daily_priorities[date_iso]
    return True


def clear_tasks_priority(
    state: AppState,
    task_ids: list[str],
    date_iso: str,
) -> int:
    changed = 0
    for task_id in task_ids:
        if clear_task_priority_for_day(state, task_id, date_iso):
            changed += 1
    return changed


def assign_tasks_priority(
    state: AppState,
    task_ids: list[str],
    date_iso: str,
    priority: int,
) -> int:
    changed = 0
    for task_id in task_ids:
        if assign_task_priority_for_day(state, task_id, date_iso, priority):
            changed += 1
    return changed


def assign_task_priority_for_day(
    state: AppState,
    task_id: str,
    date_iso: str,
    priority: int,
) -> bool:
    priority = _clamp_priority(priority)
    task = _find_task(state, task_id)
    if task.daily_priorities.get(date_iso) == priority:
        return False
    task.daily_priorities[date_iso] = priority
    return True


def _stored_priority(value: object) -> int | None:
    if not isinstance(value, int):
        return None
    if value < MIN_PRIORITY or value > MAX_PRIORITY:
        return None
    return value


def merge_daily_priorities(
    left: dict[str, int] | None,
    right: dict[str, int] | None,
) -> dict[str, int]:
    left_map = left or {}
    right_map = right or {}
    merged: dict[str, int] = {}
    for key in set(left_map) | set(right_map):
        left_value = _stored_priority(left_map.get(key))
        right_value = _stored_priority(right_map.get(key))
        if left_value is None and right_value is None:
            continue
        if left_value is not None and right_value is not None:
            merged[key] = min(left_value, right_value)
        elif left_value is not None:
            merged[key] = left_value
        else:
            merged[key] = right_value
    return merged


def priority_filter_levels(ui: dict) -> set[int]:
    raw = ui.get("priority_filter", [1, 2, 3, 4])
    if not isinstance(raw, list):
        return set(ALL_PRIORITIES)
    levels = {int(value) for value in raw if isinstance(value, int) and value in ALL_PRIORITIES}
    return levels or set(ALL_PRIORITIES)


def set_priority_filter_levels(ui: dict, levels: set[int]) -> bool:
    if not levels:
        return False
    normalized = sorted(level for level in levels if level in ALL_PRIORITIES)
    if not normalized:
        return False
    if priority_filter_levels(ui) == set(normalized):
        return False
    ui["priority_filter"] = normalized
    return True
