from __future__ import annotations

from PySide6.QtCore import Qt

from timerapp_ag.ui.floating_timer import FloatingTimer


def test_floating_timer_dev_badge_metadata(qapp) -> None:
    widget = FloatingTimer()
    assert widget.dev_badge.text() == "DEV"
    assert widget.dev_badge.objectName() == "floatingDevBadge"


def test_floating_timer_dev_badge_above_task_name(qapp) -> None:
    widget = FloatingTimer()
    widget.show()
    qapp.processEvents()

    assert widget.dev_badge.y() < widget.name_label.y()
    assert widget.close_button.y() <= widget.dev_badge.y() + 2
    assert widget.dev_badge.x() < widget.close_button.x()


def test_floating_timer_name_row_uses_card_width(qapp) -> None:
    widget = FloatingTimer()
    widget.show()
    qapp.processEvents()

    assert widget.name_label.width() >= 180


def test_floating_timer_update_view_elides_long_title(qapp) -> None:
    widget = FloatingTimer()
    widget.show()
    qapp.processEvents()

    long_title = "З" * 200
    widget.update_view(long_title, "01:02:03", running=True)

    shown = widget.name_label.text()
    assert len(shown) < len(long_title)
    assert widget.time_label.text() == "01:02:03"


def test_floating_timer_update_view_running_controls(qapp) -> None:
    widget = FloatingTimer()
    widget.update_view("Task", "00:01:00", running=True)

    assert widget.stop_button.isEnabled()
    assert not widget.start_button.isEnabled()


def test_floating_timer_update_view_paused_controls(qapp) -> None:
    widget = FloatingTimer()
    widget.update_view("Task", "00:01:00", running=False)

    assert not widget.stop_button.isEnabled()
    assert widget.start_button.isEnabled()
