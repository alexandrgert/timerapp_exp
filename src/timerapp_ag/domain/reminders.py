from __future__ import annotations

from datetime import date, datetime, timedelta

from ..models import Task
from .constants import (
    DEFAULT_REMINDER_INTERVAL_MINUTES,
    REMINDER_GRACE_MINUTES,
    REMINDER_INTERVAL_MAX,
    REMINDER_INTERVAL_MIN,
    default_ui,
)
from .queries import active_task, find_task
from .state import AppState


def clamp_reminder_interval(raw: object) -> int:
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = DEFAULT_REMINDER_INTERVAL_MINUTES
    return max(REMINDER_INTERVAL_MIN, min(value, REMINDER_INTERVAL_MAX))


def reminder_interval_minutes(state: AppState) -> int:
    return clamp_reminder_interval(state.ui.get("reminder_interval_minutes", DEFAULT_REMINDER_INTERVAL_MINUTES))


def reminder_interval_td(state: AppState) -> timedelta:
    return timedelta(minutes=reminder_interval_minutes(state))


def reminder_grace() -> timedelta:
    return timedelta(minutes=REMINDER_GRACE_MINUTES)


def rebuild_next_reminder_at(state: AppState) -> datetime | None:
    active = active_task(state)
    if active and active.active_session():
        return active.active_session().start_dt + reminder_interval_td(state)
    return None


def focus_timer(state: AppState) -> dict[str, object]:
    defaults = default_ui()["focus_timer"]
    focus = state.ui.setdefault("focus_timer", dict(defaults))
    for key, value in defaults.items():
        focus.setdefault(key, value)
    return focus


def focus_remaining_seconds(state: AppState, *, now: datetime | None = None) -> int:
    now = now or datetime.now()
    ends_at = focus_timer(state).get("ends_at")
    if not ends_at:
        return 0
    end_dt = datetime.fromisoformat(str(ends_at))
    return max(0, int((end_dt - now).total_seconds()))


def check_focus_timer(state: AppState, *, now: datetime | None = None) -> tuple[str, int | None]:
    now = now or datetime.now()
    timer = focus_timer(state)
    ends_at = timer.get("ends_at")
    if not ends_at:
        return ("idle", None)
    end_dt = datetime.fromisoformat(str(ends_at))
    if now >= end_dt:
        duration_minutes = timer.get("duration_minutes")
        timer["ends_at"] = None
        timer["duration_minutes"] = None
        if isinstance(duration_minutes, int):
            return ("finished", duration_minutes)
        return ("finished", None)
    return ("running", focus_remaining_seconds(state, now=now))


def check_reminders(
    state: AppState,
    *,
    now: datetime | None = None,
    pending_confirmation_task_id: str | None,
    pending_confirmation_deadline: datetime | None,
    next_reminder_at: datetime | None,
) -> tuple[str, Task | None, str | None, datetime | None, datetime | None, bool]:
    """
    Evaluate reminder state.

    Returns:
        status, active_task, new_pending_id, new_pending_deadline, new_next_reminder_at, needs_save
    """
    now = now or datetime.now()
    active = active_task(state)
    if active is None:
        return ("idle", None, None, None, None, False)

    if pending_confirmation_task_id == active.id and pending_confirmation_deadline:
        if now >= pending_confirmation_deadline:
            from .task_ops import stop_task

            stop_task(state, active.id, now=now)
            return ("auto_stopped", active, None, None, None, True)
        return ("awaiting_confirmation", active, pending_confirmation_task_id, pending_confirmation_deadline, next_reminder_at, False)

    if next_reminder_at and now >= next_reminder_at:
        return (
            "needs_confirmation",
            active,
            active.id,
            now + reminder_grace(),
            next_reminder_at,
            True,
        )

    rebuilt = next_reminder_at
    if rebuilt is None:
        session = active.active_session()
        started_at = session.start_dt if session else now
        rebuilt = started_at + reminder_interval_td(state)
    return ("running", active, pending_confirmation_task_id, pending_confirmation_deadline, rebuilt, False)
