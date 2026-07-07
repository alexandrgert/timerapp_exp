from __future__ import annotations

from datetime import date, timedelta

import pytest

from timerapp_ag.controller import AppController
from timerapp_ag.domain import merge as merge_domain
from timerapp_ag.domain import priority as priority_domain
from timerapp_ag.domain import queries
from timerapp_ag.models import Session, Task, TaskStatus, make_id


def _add(controller: AppController, title: str, *, planned_days: list[str] | None = None) -> Task:
    task = Task(
        id=make_id(),
        day=controller.today_str(),
        title=title,
        planned_days=list(planned_days or [controller.today_str()]),
    )
    controller.state.tasks.append(task)
    return task


def test_task_priority_defaults_to_four(controller: AppController) -> None:
    task = _add(controller, "Default")
    today = controller.today_str()
    assert priority_domain.task_priority(task, today) == 4
    assert "daily_priorities" not in task.to_dict()


def test_set_task_priority_persists_and_clears_default(controller: AppController) -> None:
    task = _add(controller, "Priority")
    today = controller.today_str()
    assert priority_domain.set_task_priority(controller.state, task.id, today, 1)
    assert task.daily_priorities[today] == 1
    assert priority_domain.set_task_priority(controller.state, task.id, today, 4)
    assert today not in task.daily_priorities


def test_set_task_priority_rejects_invalid_level(controller: AppController) -> None:
    task = _add(controller, "Bad")
    with pytest.raises(ValueError):
        priority_domain.set_task_priority(controller.state, task.id, controller.today_str(), 0)


def test_set_tasks_priority_bulk(controller: AppController) -> None:
    first = _add(controller, "A")
    second = _add(controller, "B")
    today = controller.today_str()
    changed = priority_domain.set_tasks_priority(controller.state, [first.id, second.id], today, 2)
    assert changed == 2
    assert priority_domain.task_priority(first, today) == 2
    assert priority_domain.task_priority(second, today) == 2


def test_filter_tasks_by_priority(controller: AppController) -> None:
    high = _add(controller, "High")
    low = _add(controller, "Low")
    today = controller.today_str()
    priority_domain.set_task_priority(controller.state, high.id, today, 1)
    priority_domain.set_task_priority(controller.state, low.id, today, 3)
    filtered = priority_domain.filter_tasks_by_priority(
        controller.state.tasks,
        today,
        {1, 3},
    )
    assert {task.title for task in filtered} == {"High", "Low"}


def test_tasks_today_plan_filters_and_sorts_by_priority(controller: AppController) -> None:
    today = controller.today_str()
    high = _add(controller, "High")
    low = _add(controller, "Low")
    priority_domain.set_task_priority(controller.state, high.id, today, 1)
    priority_domain.set_task_priority(controller.state, low.id, today, 4)
    controller.state.ui["priority_filter"] = [1]
    tasks = controller.tasks_today_plan()
    assert [task.title for task in tasks] == ["High"]


def test_tasks_today_plan_sorts_completed_after_open(controller: AppController) -> None:
    today = controller.today_str()
    done = _add(controller, "Done", planned_days=[today])
    open_task = _add(controller, "Open", planned_days=[today])
    done.status = TaskStatus.COMPLETED
    priority_domain.set_task_priority(controller.state, done.id, today, 1)
    priority_domain.set_task_priority(controller.state, open_task.id, today, 4)
    tasks = controller.tasks_today_plan()
    assert [task.title for task in tasks] == ["Open", "Done"]


def test_merge_daily_priorities_prefers_higher_priority() -> None:
    merged = priority_domain.merge_daily_priorities({"2026-07-06": 2}, {"2026-07-06": 1})
    assert merged == {"2026-07-06": 1}


def test_merge_task_pair_merges_daily_priorities() -> None:
    task_id = make_id()
    left = Task(id=task_id, day="2026-07-06", title="T", daily_priorities={"2026-07-06": 3})
    right = Task(id=task_id, day="2026-07-06", title="T", daily_priorities={"2026-07-06": 1})
    merged = merge_domain.merge_task_pair(left, right)
    assert merged.daily_priorities == {"2026-07-06": 1}


def test_merge_daily_priorities_ignores_invalid_values() -> None:
    merged = priority_domain.merge_daily_priorities(
        {"2026-07-06": 0, "2026-07-07": 99},
        {"2026-07-06": 2},
    )
    assert merged == {"2026-07-06": 2}


def test_merge_daily_priorities_preserves_explicit_four() -> None:
    merged = priority_domain.merge_daily_priorities(
        {"2026-07-07": 4},
        {},
    )
    assert merged == {"2026-07-07": 4}


def test_merge_daily_priorities_prefers_higher_priority_over_explicit_four() -> None:
    merged = priority_domain.merge_daily_priorities(
        {"2026-07-07": 4},
        {"2026-07-07": 2},
    )
    assert merged == {"2026-07-07": 2}


def test_task_from_dict_filters_invalid_daily_priorities() -> None:
    task = Task.from_dict(
        {
            "id": make_id(),
            "day": "2026-07-07",
            "title": "Robustness",
            "status": TaskStatus.OPEN.value,
            "sessions": [],
            "daily_priorities": {
                "2026-07-07": 2,
                "2026-07-08": 0,
                "2026-07-09": 9,
            },
        }
    )
    assert task.daily_priorities == {"2026-07-07": 2}


def test_task_priority_falls_back_to_default_for_invalid_stored_value() -> None:
    task = Task(
        id=make_id(),
        day="2026-07-07",
        title="Invalid stored",
        daily_priorities={"2026-07-07": 99},
    )
    assert priority_domain.task_priority(task, "2026-07-07") == 4


def test_priority_filter_levels_defaults_to_all(controller: AppController) -> None:
    assert controller.priority_filter_levels() == {1, 2, 3, 4}


def test_set_priority_filter_levels_requires_non_empty(controller: AppController) -> None:
    assert not priority_domain.set_priority_filter_levels(controller.state.ui, set())
    controller.set_priority_filter_levels({1, 2})
    assert controller.priority_filter_levels() == {1, 2}


def test_tasks_today_plan_uses_controller_filter(controller: AppController) -> None:
    today = controller.today_str()
    first = _add(controller, "One")
    second = _add(controller, "Two")
    priority_domain.set_task_priority(controller.state, first.id, today, 1)
    priority_domain.set_task_priority(controller.state, second.id, today, 2)
    controller.set_priority_filter_levels({2})
    titles = [task.title for task in controller.tasks_today_plan()]
    assert titles == ["Two"]


def test_tasks_today_plan_hides_old_default_priority_without_today_override(
    controller: AppController,
) -> None:
    today = controller.today_str()
    old_task = Task(
        id=make_id(),
        day="2026-07-06",
        title="Old default",
        planned_days=[today],
    )
    explicit_today = Task(
        id=make_id(),
        day="2026-07-06",
        title="Old explicit today",
        planned_days=[today],
        daily_priorities={today: 4},
    )
    created_today = Task(
        id=make_id(),
        day=today,
        title="Created today",
        planned_days=[today],
    )
    controller.state.tasks.extend([old_task, explicit_today, created_today])

    titles = {task.title for task in controller.tasks_today_plan(today)}

    assert "Old default" not in titles
    assert "Old explicit today" in titles
    assert "Created today" in titles


def test_assign_task_priority_for_day_persists_default_priority(
    controller: AppController,
) -> None:
    today = controller.today_str()
    task = _add(controller, "Persist default", planned_days=[])
    changed = priority_domain.assign_task_priority_for_day(
        controller.state,
        task.id,
        today,
        priority_domain.DEFAULT_PRIORITY,
    )
    assert changed is True
    assert task.daily_priorities[today] == 4


def test_add_to_plan_with_priority_shows_old_task_on_today_plan(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Plan me",
        planned_days=[],
    )
    controller.state.tasks.append(task)

    controller.add_to_plan_with_priority(task.id, 2)

    titles = {item.title for item in controller.tasks_today_plan(today)}
    assert "Plan me" in titles
    assert today in controller.find_task(task.id).planned_days
    assert controller.task_priority(controller.find_task(task.id), today) == 2


def test_start_task_adds_old_task_to_today_plan(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Started from all",
        planned_days=[yesterday],
    )
    controller.state.tasks.append(task)

    controller.set_tasks_priority([task.id], 1)
    controller.start_task(task.id)

    titles = {item.title for item in controller.tasks_today_plan(today)}
    assert "Started from all" in titles
    assert today in controller.find_task(task.id).planned_days


def test_set_tasks_priority_adds_non_default_task_to_today_plan(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Priority only",
        planned_days=[yesterday],
    )
    controller.state.tasks.append(task)

    controller.set_tasks_priority([task.id], 2)

    titles = {item.title for item in controller.tasks_today_plan(today)}
    assert "Priority only" in titles
    assert today in controller.find_task(task.id).planned_days


def test_tasks_today_plan_shows_running_old_default_task(
    controller: AppController,
) -> None:
    today = controller.today_str()
    running_old = Task(
        id=make_id(),
        day="2026-07-06",
        title="Running old default",
        planned_days=[today],
        status=TaskStatus.RUNNING,
        sessions=[
            Session(
                id=make_id(),
                started_at=f"{today}T10:00:00",
                ended_at=None,
            )
        ],
    )
    controller.state.tasks.append(running_old)

    titles = {task.title for task in controller.tasks_today_plan(today)}

    assert "Running old default" in titles


def test_assign_then_edit_priority_four_keeps_old_task_on_today_plan(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Planned old",
        planned_days=[],
    )
    controller.state.tasks.append(task)

    controller.add_to_plan_with_priority(task.id, 4)
    controller.assign_tasks_priority([task.id], 4)

    titles = {item.title for item in controller.tasks_today_plan(today)}
    assert "Planned old" in titles
    assert controller.find_task(task.id).daily_priorities[today] == 4


def test_bulk_assign_priority_four_keeps_old_task_on_today_plan(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Low priority",
        planned_days=[],
    )
    controller.state.tasks.append(task)

    controller.add_to_plan_with_priority(task.id, 2)
    controller.assign_tasks_priority([task.id], 4, add_to_plan=True)

    stored = controller.find_task(task.id)
    assert stored.daily_priorities[today] == 4
    titles = {item.title for item in controller.tasks_today_plan(today)}
    assert "Low priority" in titles
    assert today in stored.planned_days


def test_set_tasks_priority_four_clears_override_and_hides_old_task(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Reset me",
        planned_days=[],
    )
    controller.state.tasks.append(task)

    controller.add_to_plan_with_priority(task.id, 2)
    controller.set_tasks_priority([task.id], 4)

    stored = controller.find_task(task.id)
    assert today not in stored.daily_priorities
    titles = {item.title for item in controller.tasks_today_plan(today)}
    assert "Reset me" not in titles
    assert today in stored.planned_days


def test_plan_rollover_carried_task_not_visible_on_today_plan(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Rolled over",
        planned_days=[yesterday],
        status=TaskStatus.OPEN,
    )
    controller.state.tasks.append(task)
    controller.state.ui["plan_rollover_day"] = yesterday

    controller.ensure_plan_rollover(today)

    stored = controller.find_task(task.id)
    assert today in stored.planned_days
    assert today not in stored.daily_priorities
    titles = {item.title for item in controller.tasks_today_plan(today)}
    assert "Rolled over" not in titles


def test_rollover_in_today_plan_but_not_visible_on_today_tab(
    controller: AppController,
) -> None:
    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Rolled over",
        planned_days=[yesterday],
        status=TaskStatus.OPEN,
    )
    controller.state.tasks.append(task)
    controller.state.ui["plan_rollover_day"] = yesterday

    controller.ensure_plan_rollover(today)

    stored = controller.find_task(task.id)
    assert controller.in_today_plan(stored, today)
    assert not controller.visible_on_today_plan(stored, today)


def test_running_task_stays_on_today_plan_when_priority_filtered_out(
    controller: AppController,
) -> None:
    today = controller.today_str()
    running = Task(
        id=make_id(),
        day="2026-07-06",
        title="Running filtered",
        planned_days=[today],
        status=TaskStatus.RUNNING,
        sessions=[
            Session(
                id=make_id(),
                started_at=f"{today}T10:00:00",
                ended_at=None,
            )
        ],
    )
    controller.state.tasks.append(running)
    controller.set_priority_filter_levels({1, 2, 3})

    titles = {task.title for task in controller.tasks_today_plan(today)}

    assert "Running filtered" in titles
