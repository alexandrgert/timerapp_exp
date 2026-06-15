"""Доменный слой: бизнес-логика без UI и без I/O."""

from .formatting import format_day_label, format_duration, format_hm
from .merge import merge_states, pick_best_data_file, score_data_file, states_equivalent, task_richer
from .plan import ensure_plan_rollover, migrate_schema_v2
from .queries import active_task, find_task, running_tasks, today_str
from .state import AppState

__all__ = [
    "AppState",
    "active_task",
    "ensure_plan_rollover",
    "find_task",
    "format_day_label",
    "format_duration",
    "format_hm",
    "merge_states",
    "migrate_schema_v2",
    "pick_best_data_file",
    "running_tasks",
    "score_data_file",
    "states_equivalent",
    "task_richer",
    "today_str",
]
