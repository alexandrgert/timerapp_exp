from __future__ import annotations

from datetime import datetime, timedelta

from timerapp_ag.controller import AppController
from timerapp_ag.domain.day_report import build_day_report_markdown
from timerapp_ag.domain.state import AppState
from timerapp_ag.models import Session, Task, TaskStatus


def _task_with_sessions(
    *,
    title: str = "Task A",
    description: str = "",
    result: str = "",
    day: str = "2026-07-10",
) -> Task:
    start = datetime(2026, 7, 10, 10, 0, 0)
    return Task(
        id="t1",
        day=day,
        title=title,
        description=description,
        result=result,
        status=TaskStatus.PAUSED,
        sessions=[
            Session(
                id="s1",
                started_at=start.isoformat(),
                ended_at=(start + timedelta(hours=2, minutes=15)).isoformat(),
                comment="Первая сессия",
                bitrix_record_id="42",
            ),
            Session(
                id="s2",
                started_at=datetime(2026, 7, 9, 12, 0, 0).isoformat(),
                ended_at=datetime(2026, 7, 9, 13, 0, 0).isoformat(),
            ),
        ],
    )


def test_build_day_report_includes_total_result_and_sorting() -> None:
    slow = _task_with_sessions(title="Slow task", result="Готово")
    fast = Task(
        id="t2",
        day="2026-07-10",
        title="Fast task",
        sessions=[
            Session(
                id="s3",
                started_at=datetime(2026, 7, 10, 14, 0, 0).isoformat(),
                ended_at=datetime(2026, 7, 10, 15, 30, 0).isoformat(),
            )
        ],
    )
    state = AppState(tasks=[slow, fast])
    report = build_day_report_markdown(state, "2026-07-10")

    assert "# Отчёт за 10.07.2026" in report
    assert "**Итого:** 03:45" in report
    assert report.index("Slow task") < report.index("Fast task")
    assert "**Результат:** Готово" in report
    assert "Описание" not in report
    assert "Сессии за день" not in report


def test_build_day_report_omits_empty_result() -> None:
    task = _task_with_sessions(result="")
    state = AppState(tasks=[task])
    report = build_day_report_markdown(state, "2026-07-10")
    assert "**Результат:**" not in report


def test_build_day_report_empty_day() -> None:
    state = AppState(tasks=[])
    report = build_day_report_markdown(state, "2026-07-10")
    assert "время не учтено" in report


def test_build_day_report_extended_includes_description_and_sessions() -> None:
    task = _task_with_sessions(
        description="Подробное описание",
        result="Итог",
    )
    state = AppState(tasks=[task])
    report = build_day_report_markdown(state, "2026-07-10", extended=True)

    assert "### Описание" in report
    assert "Подробное описание" in report
    assert "### Сессии за день" in report
    assert "Первая сессия" in report
    assert "42" in report
    assert "10.07.2026 10:00" in report


def test_controller_build_day_report(controller: AppController) -> None:
    task = controller.create_task("Work")
    now = datetime.now()
    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    controller.add_session(task.id, start, start + timedelta(minutes=30))
    controller.complete_task(task.id, result="Сделано")
    report = controller.build_day_report(controller.today_str())
    assert "Work" in report
    assert "Сделано" in report
