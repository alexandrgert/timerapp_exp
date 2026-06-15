from __future__ import annotations

from timerapp_ag.controller import AppController
from timerapp_ag.main_window import (
    format_tray_tooltip,
    main_window_is_open,
    resolve_floating_task,
    tray_activation_is_debounced,
    tray_tooltip_task_titles,
)
from timerapp_ag.models import Task, TaskStatus
from timerapp_ag.storage import Storage


def test_running_tasks_returns_active_timer(controller: AppController) -> None:
    task = controller.create_task("Alpha", start_now=True)
    running = controller.running_tasks()
    assert len(running) == 1
    assert running[0].id == task.id


def test_running_tasks_empty_when_stopped(controller: AppController) -> None:
    task = controller.create_task("Beta", start_now=True)
    controller.stop_task(task.id)
    assert controller.running_tasks() == []


def test_format_tray_tooltip_window_visible_shows_app_title() -> None:
    text = format_tray_tooltip(
        window_visible=True,
        app_title="TaskTimer link B24 0.2.2",
        task_titles=["Задача A"],
    )
    assert text == "TaskTimer link B24 0.2.2"


def test_format_tray_tooltip_hidden_shows_one_task_per_line() -> None:
    text = format_tray_tooltip(
        window_visible=False,
        app_title="TaskTimer link B24 0.2.2",
        task_titles=["Задача A", "Задача B"],
    )
    assert text == "Задача A\nЗадача B"


def test_format_tray_tooltip_hidden_without_tasks_shows_idle_hint() -> None:
    text = format_tray_tooltip(
        window_visible=False,
        app_title="TaskTimer link B24 0.2.2",
        task_titles=[],
    )
    assert text == "Нет активных таймеров"


def test_tray_tooltip_task_titles_includes_paused_floating_task() -> None:
    paused = Task(id="p1", day="2026-06-15", title="Paused task", status=TaskStatus.PAUSED)
    titles = tray_tooltip_task_titles(
        running_task_titles=[],
        floating_task=paused,
    )
    assert titles == ["Paused task"]


def test_tray_tooltip_task_titles_deduplicates_running_and_floating() -> None:
    running = Task(id="r1", day="2026-06-15", title="Same", status=TaskStatus.RUNNING)
    titles = tray_tooltip_task_titles(
        running_task_titles=["Same"],
        floating_task=running,
    )
    assert titles == ["Same"]


def test_resolve_floating_task_returns_paused_tracked_task(controller: AppController) -> None:
    task = controller.create_task("Paused", start_now=True)
    controller.stop_task(task.id)

    resolved, tracked = resolve_floating_task(
        active=None,
        tracked_task_id=task.id,
        find_task=controller.find_task,
    )
    assert resolved is not None
    assert resolved.id == task.id
    assert tracked == task.id


def test_resolve_floating_task_hides_completed_task(controller: AppController) -> None:
    task = controller.create_task("Done", start_now=True)
    controller.complete_task(task.id)

    resolved, tracked = resolve_floating_task(
        active=None,
        tracked_task_id=task.id,
        find_task=controller.find_task,
    )
    assert resolved is None
    assert tracked is None


def test_resolve_floating_task_active_overrides_tracked(controller: AppController) -> None:
    tracked = controller.create_task("Tracked paused", start_now=True)
    controller.stop_task(tracked.id)
    active = controller.create_task("Active running", start_now=True)

    resolved, tracked_id = resolve_floating_task(
        active=controller.active_task(),
        tracked_task_id=tracked.id,
        find_task=controller.find_task,
    )
    assert resolved is not None
    assert resolved.id == active.id
    assert tracked_id == active.id


def test_resolve_floating_task_open_clears_tracking(controller: AppController) -> None:
    task = controller.create_task("Open only", start_now=False)

    resolved, tracked = resolve_floating_task(
        active=None,
        tracked_task_id=task.id,
        find_task=controller.find_task,
    )
    assert resolved is None
    assert tracked is None


def test_main_window_is_open() -> None:
    assert main_window_is_open(is_visible=True, is_minimized=False) is True
    assert main_window_is_open(is_visible=True, is_minimized=True) is False
    assert main_window_is_open(is_visible=False, is_minimized=False) is False


def test_tray_activation_debounce_blocks_rapid_repeats() -> None:
    assert tray_activation_is_debounced(now=1.0, last_at=0.0) is False
    assert tray_activation_is_debounced(now=1.1, last_at=1.0) is True
    assert tray_activation_is_debounced(now=1.5, last_at=1.0) is False
