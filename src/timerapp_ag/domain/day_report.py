from __future__ import annotations

from datetime import datetime

from ..models import Session, Task
from .datetime_util import session_local_date
from .formatting import format_day_label, format_hm, format_task_datetime
from .queries import today_seconds, today_total_seconds
from .state import AppState


def _sessions_on_date(task: Task, date_iso: str) -> list[Session]:
    return [
        session
        for session in task.sessions
        if session_local_date(session.started_at) == date_iso
    ]


def _session_ended_label(session: Session) -> str:
    if session.ended_at is None:
        return "идёт"
    return format_task_datetime(session.ended_at)


def _session_transferred_label(session: Session) -> str:
    return session.bitrix_record_id or ""


def _format_task_section(
    task: Task,
    date_iso: str,
    *,
    extended: bool,
    now: datetime | None,
) -> list[str]:
    seconds = today_seconds(task, date_iso, now=now)
    lines = [f"## {task.title} — {format_hm(seconds)}"]
    result = task.result.strip()
    if result:
        lines.append("")
        lines.append(f"**Результат:** {result}")
    if not extended:
        return lines

    description = task.description.strip()
    if description:
        lines.append("")
        lines.append("### Описание")
        lines.append(description)

    day_sessions = _sessions_on_date(task, date_iso)
    if day_sessions:
        lines.append("")
        lines.append("### Сессии за день")
        lines.append("| Начало | Окончание | Длительность | Комментарий | Передано |")
        lines.append("| --- | --- | --- | --- | --- |")
        for session in day_sessions:
            comment = session.comment.replace("|", "\\|").replace("\n", " ")
            transferred = _session_transferred_label(session).replace("|", "\\|")
            lines.append(
                "| {start} | {end} | {duration} | {comment} | {transferred} |".format(
                    start=format_task_datetime(session.started_at),
                    end=_session_ended_label(session),
                    duration=format_hm(session.duration_seconds(now=now)),
                    comment=comment,
                    transferred=transferred,
                )
            )
    return lines


def build_day_report_markdown(
    state: AppState,
    date_iso: str,
    *,
    extended: bool = False,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now()
    day_label = format_day_label(date_iso)
    tasks = [
        task
        for task in state.tasks
        if today_seconds(task, date_iso, now=now) > 0
    ]
    tasks.sort(key=lambda task: today_seconds(task, date_iso, now=now), reverse=True)
    if not tasks:
        return f"# Отчёт за {day_label}\n\nЗа {day_label} время не учтено."

    total_seconds = today_total_seconds(state, date_iso, now=now)
    lines = [
        f"# Отчёт за {day_label}",
        "",
        f"**Итого:** {format_hm(total_seconds)}",
        "",
    ]
    for index, task in enumerate(tasks):
        if index > 0:
            lines.append("")
        lines.extend(
            _format_task_section(task, date_iso, extended=extended, now=now)
        )
    return "\n".join(lines)
