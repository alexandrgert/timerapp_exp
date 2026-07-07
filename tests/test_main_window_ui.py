from __future__ import annotations

from datetime import datetime

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from timerapp_ag.controller import AppController
from timerapp_ag.domain import queries
from timerapp_ag.domain.formatting import format_hm
from timerapp_ag.main_window import (
    CreateTaskDialog,
    MainWindow,
    SessionEditDialog,
    TaskEditDialog,
    TaskRow,
    RIGHT_COLUMN_WIDTH,
    SIDEBAR_WIDTH,
    SUMMARY_LABEL_SAMPLE,
    TASK_LIST_MIN_WIDTH,
    TASK_ROW_DESC_HORIZONTAL_INSET,
    TASK_ROW_NAME_MIN_WIDTH,
    TASK_ROW_PINNED_FOOTER_V_PAD,
    TIMER_CARD_STATS_SPACING,
    TIMER_DIGITS_FONT_SIZE,
    TIMER_DIGITS_VERTICAL_PAD,
    break_long_unbroken_runs,
    fit_plain_text_edit_height,
    fit_wrapped_label_height,
)
from timerapp_ag.models import Task, TaskStatus, make_id


def _widget_right_in_ancestor(widget: QWidget, ancestor: QWidget, *, margin: int = 0) -> int:
    return widget.mapTo(ancestor, widget.rect().topRight()).x() - margin


def _assert_settings_tab_fits_or_scrolls(scroll: QScrollArea) -> None:
    inner = scroll.widget()
    assert inner is not None
    if scroll.viewport().height() >= inner.minimumHeight():
        return
    assert scroll.verticalScrollBar().maximum() > 0


def _settings_dialog_tabs(dialog) -> QTabWidget:
    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    return tabs

@pytest.fixture
def main_window(
    qapp: QApplication, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> MainWindow:
    monkeypatch.setattr("timerapp_ag.main_window.QTimer.singleShot", lambda *args, **kwargs: None)
    window = MainWindow(controller, qapp)
    original_refresh_ui = window.refresh_ui

    def refresh_ui_with_flush() -> None:
        original_refresh_ui()
        qapp.processEvents()

    window.refresh_ui = refresh_ui_with_flush  # type: ignore[method-assign]
    qapp.processEvents()
    yield window
    window.close()


def test_main_window_has_sidebar_and_tasks_page(main_window: MainWindow) -> None:
    assert main_window.tasks_page is not None
    assert set(main_window._view_buttons) == {"plan", "in_progress", "all"}


def test_main_window_focus_card_under_timer(main_window: MainWindow) -> None:
    assert main_window.focus_section is not None
    assert main_window.focus_card is not None
    assert main_window.focus_display is not None
    assert main_window.focus_status_label is not None
    assert main_window.focus_stop_button is not None
    assert set(main_window.focus_buttons) == set(main_window.focus_presets)
    assert main_window.right_column is not None


def test_focus_card_always_visible_on_tasks_page(main_window: MainWindow) -> None:
    assert not main_window.focus_section.isHidden()


def test_main_window_timer_panel_widgets_exist(main_window: MainWindow) -> None:
    assert main_window.timer_digits is not None
    assert main_window.timer_today_value is not None
    assert main_window.timer_total_value is not None
    assert main_window.stop_active_button is not None
    assert main_window.complete_active_button is not None


def test_timer_digits_keeps_minimum_height_with_long_task_name(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    long_name = "Лаб Правосудия: " + "очень длинное название " * 5
    task = controller.create_task(long_name, start_now=True)
    controller.stop_task(task.id)
    main_window.refresh_ui()
    main_window.show()
    qapp.processEvents()

    font = QFont(main_window._mono_family, TIMER_DIGITS_FONT_SIZE)
    font.setWeight(QFont.Weight.Light)
    metrics = QFontMetrics(font)
    expected_height = metrics.boundingRect("00:00:00").height() + TIMER_DIGITS_VERTICAL_PAD
    assert main_window.timer_digits.height() == expected_height


def test_timer_stats_do_not_overlap_digits_with_long_task_name(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    long_name = "Лаб Правосудия: " + "очень длинное название " * 4
    task = controller.create_task(long_name, start_now=True)
    controller.stop_task(task.id)
    main_window.refresh_ui()
    main_window.show()
    qapp.processEvents()

    digits_bottom = main_window.timer_digits.mapTo(
        main_window.timer_card,
        main_window.timer_digits.rect().bottomLeft(),
    ).y()
    stats_top = main_window.timer_today_value.mapTo(
        main_window.timer_card,
        main_window.timer_today_value.rect().topLeft(),
    ).y()
    assert stats_top >= digits_bottom + TIMER_CARD_STATS_SPACING - 1


def test_timer_continue_button_does_not_overlap_stats_with_long_title(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    long_name = "Лаб Правосудия: " + "длинное название " * 5
    task = controller.create_task(long_name, start_now=True)
    controller.stop_task(task.id)
    main_window.show()
    main_window.refresh_ui()
    qapp.processEvents()

    panel = main_window.timer_panel
    stats_bottom = main_window.timer_today_value.mapTo(
        panel,
        main_window.timer_today_value.rect().bottomLeft(),
    ).y()
    button_top = main_window.stop_active_button.mapTo(
        panel,
        main_window.stop_active_button.rect().topLeft(),
    ).y()
    card_bottom = main_window.timer_card.mapTo(
        panel,
        main_window.timer_card.rect().bottomLeft(),
    ).y()
    assert main_window.stop_active_button.text() == "Продолжить"
    assert button_top >= stats_bottom + 16
    assert button_top >= card_bottom + 16


def test_focus_section_does_not_overlap_complete_button(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    long_name = "Лаб Правосудия: " + "длинное название " * 5
    task = controller.create_task(long_name, start_now=True)
    controller.stop_task(task.id)
    main_window.show()
    main_window.refresh_ui()
    qapp.processEvents()

    panel = main_window.timer_panel
    complete_bottom = main_window.complete_active_button.mapTo(
        panel,
        main_window.complete_active_button.rect().bottomLeft(),
    ).y()
    focus_top = main_window.focus_section.mapTo(
        panel,
        main_window.focus_section.rect().topLeft(),
    ).y()
    assert focus_top >= complete_bottom + 8


def test_main_window_min_height_shows_focus_stop_button(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    long_name = "Лаб Правосудия: " + "длинное название " * 5
    task = controller.create_task(long_name, start_now=True)
    controller.stop_task(task.id)
    main_window.show()
    main_window.refresh_ui()
    qapp.processEvents()

    main_window.resize(main_window.minimumWidth(), main_window.minimumHeight())
    qapp.processEvents()

    stop_bottom = main_window.focus_stop_button.mapTo(
        main_window,
        main_window.focus_stop_button.rect().bottomLeft(),
    ).y()
    assert main_window.focus_stop_button.isVisibleTo(main_window)
    assert stop_bottom <= main_window.height()
    assert main_window.minimumHeight() >= main_window.timer_panel.sizeHint().height()


def test_focus_card_aligns_with_timer_card(
    main_window: MainWindow, qapp: QApplication
) -> None:
    main_window.show()
    qapp.processEvents()

    panel = main_window.timer_panel
    card_left = main_window.timer_card.mapTo(
        panel, main_window.timer_card.rect().topLeft()
    ).x()
    focus_left = main_window.focus_card.mapTo(
        panel, main_window.focus_card.rect().topLeft()
    ).x()
    assert focus_left == card_left
    assert main_window.focus_card.width() == main_window.timer_card.width()


def test_focus_preset_buttons_do_not_overlap(
    main_window: MainWindow, qapp: QApplication
) -> None:
    main_window.show()
    qapp.processEvents()

    card = main_window.focus_card
    button_rects: list[tuple[int, int, int, int]] = []
    for button in main_window.focus_buttons.values():
        top_left = button.mapTo(card, button.rect().topLeft())
        button_rects.append(
            (
                top_left.x(),
                top_left.y(),
                top_left.x() + button.width(),
                top_left.y() + button.height(),
            )
        )

    for left, top, right, bottom in button_rects:
        assert bottom - top > 0
        assert right > left

    for index, rect_a in enumerate(button_rects):
        for rect_b in button_rects[index + 1 :]:
            separated = (
                rect_a[2] <= rect_b[0]
                or rect_b[2] <= rect_a[0]
                or rect_a[3] <= rect_b[1]
                or rect_b[3] <= rect_a[1]
            )
            assert separated

    preset_bottom = max(bottom for *_rest, bottom in button_rects)
    stop_top = main_window.focus_stop_button.mapTo(
        card, main_window.focus_stop_button.rect().topLeft()
    ).y()
    assert stop_top >= preset_bottom + 8
    assert main_window.focus_card.height() >= main_window.focus_card.sizeHint().height()


def test_timer_card_shrinks_when_task_title_becomes_short(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    long_name = "Лаб Правосудия: " + "очень длинное название " * 4
    long_task = controller.create_task(long_name, start_now=True)
    controller.stop_task(long_task.id)
    main_window.show()
    main_window.refresh_ui()
    qapp.processEvents()
    tall_card_height = main_window.timer_card.height()

    short_task = controller.create_task("Коротко", start_now=True)
    controller.stop_task(short_task.id)
    main_window.refresh_ui()
    qapp.processEvents()

    panel_task = controller.timer_panel_task()
    assert panel_task is not None
    assert panel_task.title == "Коротко"
    short_card_height = main_window.timer_card.height()
    assert short_card_height < tall_card_height

    digits_bottom = main_window.timer_digits.mapTo(
        main_window.timer_card,
        main_window.timer_digits.rect().bottomLeft(),
    ).y()
    stats_top = main_window.timer_today_value.mapTo(
        main_window.timer_card,
        main_window.timer_today_value.rect().topLeft(),
    ).y()
    assert stats_top >= digits_bottom + TIMER_CARD_STATS_SPACING - 1


def test_show_startup_notices_uses_tray_without_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubTray:
        def isVisible(self) -> bool:
            return True

    class _StubController:
        webdav_startup_notice = "WebDAV: синхронизировано"

    window = MainWindow.__new__(MainWindow)
    window.controller = _StubController()  # type: ignore[assignment]
    window.tray_available = True
    window.tray = _StubTray()  # type: ignore[assignment]
    shown: list[int] = []
    dialogs: list[int] = []
    window._show_tray_message = lambda *args, **kwargs: shown.append(1)  # type: ignore[method-assign]
    monkeypatch.setattr(
        "timerapp_ag.main_window.QMessageBox.information",
        lambda *args, **kwargs: dialogs.append(1),
    )
    monkeypatch.setattr("timerapp_ag.main_window.clear_webdav_pending_notice", lambda: None)

    MainWindow._show_startup_notices(window)

    assert shown == [1]
    assert dialogs == []
    assert window.controller.webdav_startup_notice is None


def test_timer_panel_task_prefers_running_over_paused(controller: AppController) -> None:
    first = controller.create_task("First", start_now=True)
    controller.stop_task(first.id)
    second = controller.create_task("Second", start_now=True)

    assert queries.timer_panel_task(controller.state) is not None
    assert queries.timer_panel_task(controller.state).id == second.id

    controller.stop_task(second.id)
    panel = queries.timer_panel_task(controller.state)
    assert panel is not None
    assert panel.id == second.id


def test_timer_panel_shows_paused_task(
    main_window: MainWindow, controller: AppController, qapp: QApplication
) -> None:
    task = controller.create_task(
        "Paused work",
        description="Описание на паузе",
        start_now=True,
    )
    controller.stop_task(task.id)
    main_window.refresh_ui()
    main_window.show()
    qapp.processEvents()

    assert controller.timer_panel_task() is not None
    assert main_window.active_task_name.text() == "Paused work"
    assert main_window.stop_active_button.text() == "Продолжить"
    assert main_window.stop_active_button.isEnabled()
    assert not main_window.timer_panel.property("running")


def test_fit_wrapped_label_height_grows_for_long_text(qapp: QApplication) -> None:
    label = QLabel()
    label.setWordWrap(True)
    label.resize(200, 20)
    short = "Короткое описание"
    fit_wrapped_label_height(label, short, width=200)
    short_height = label.height()
    long_text = "слово " * 80
    fit_wrapped_label_height(label, long_text, width=200)
    assert label.height() > short_height


def test_fit_plain_text_edit_height_grows_for_long_text(qapp: QApplication) -> None:
    edit = QPlainTextEdit()
    edit.resize(400, 72)
    edit.setPlainText("строка\n" * 12)
    fit_plain_text_edit_height(edit)
    assert edit.height() > 72


def test_task_edit_dialog_description_autofit(
    controller: AppController, qapp: QApplication
) -> None:
    task = controller.create_task("T", description="строка\n" * 15)
    dialog = TaskEditDialog(controller, task)
    dialog.show()
    qapp.processEvents()
    assert dialog.description_edit.height() > 90


def test_create_task_dialog_emits_selected_priority(
    controller: AppController,
    qapp: QApplication,
) -> None:
    dialog = CreateTaskDialog(controller)
    payloads: list[dict] = []
    dialog.create_requested.connect(payloads.append)
    dialog.title_edit.setText("Priority create")
    dialog.description_edit.setPlainText("Details")
    dialog._priority_buttons[2].click()

    dialog._emit_request(False)

    assert payloads
    assert payloads[0]["priority"] == 2


def test_task_edit_dialog_saves_selected_priority(
    controller: AppController,
) -> None:
    task = controller.create_task("Edit me", description="text")
    dialog = TaskEditDialog(controller, task)
    dialog._priority_buttons[3].click()

    dialog.accept()

    reloaded = controller.find_task(task.id)
    assert controller.task_priority(reloaded) == 3


def test_session_edit_dialog_keeps_selected_row_after_save(
    controller: AppController,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = controller.create_task("History task", description="text")
    controller.add_session(
        task.id,
        datetime(2026, 7, 7, 11, 15, 3),
        datetime(2026, 7, 7, 11, 32, 41),
    )
    second = controller.add_session(
        task.id,
        datetime(2026, 7, 7, 12, 10, 3),
        datetime(2026, 7, 7, 12, 20, 41),
        comment="comment",
    )
    dialog = SessionEditDialog(controller, controller.find_task(task.id))
    monkeypatch.setattr("timerapp_ag.main_window.QMessageBox.information", lambda *args, **kwargs: None)

    dialog.table.selectRow(1)
    dialog._load_current_session()
    dialog.comment_edit.setPlainText("updated")

    dialog._save_current_session()

    assert dialog.selected_session_id == second.id
    assert dialog._current_session_id() == second.id
    assert dialog.table.currentRow() == 1


def test_task_row_update_times_refreshes_labels(
    qapp: QApplication, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = controller.create_task("Tick", start_now=True)
    row = TaskRow(controller, task)
    seconds = iter([100, 160])
    monkeypatch.setattr(controller, "today_seconds", lambda _task, _day=None: next(seconds))
    total = iter([500, 560])
    monkeypatch.setattr(
        Task,
        "total_seconds",
        lambda self, now=None: next(total),
    )

    row.update_times(controller, task)
    assert row._today_value.text() == format_hm(100)
    assert row._total_value.text() == format_hm(500)

    row.update_times(controller, task)
    assert row._today_value.text() == format_hm(160)
    assert row._total_value.text() == format_hm(560)


def test_task_row_shows_description_on_pin(
    qapp: QApplication, controller: AppController
) -> None:
    task = controller.create_task("Details", description="Подробности по задаче")
    row = TaskRow(controller, task)
    assert row._desc_wrap.isHidden()
    row.set_pinned(True)
    assert not row._desc_wrap.isHidden()
    assert row._desc_label.text() == "Подробности по задаче"
    assert row._desc_label.property("empty") is False


def test_task_row_shows_empty_description_hint(
    qapp: QApplication, controller: AppController
) -> None:
    task = controller.create_task("No desc")
    row = TaskRow(controller, task)
    row.set_pinned(True)
    assert row._desc_label.text() == "Описание не заполнено"
    assert row._desc_label.property("empty") is True


def test_task_row_hides_description_after_unpin(
    qapp: QApplication, controller: AppController
) -> None:
    task = controller.create_task("Hide me", description="Text")
    row = TaskRow(controller, task)
    row.set_pinned(True)
    row.set_pinned(False)
    assert row._desc_wrap.isHidden()


def test_task_row_second_click_collapses(
    qapp: QApplication, controller: AppController
) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    task = controller.create_task("Collapse me", description="Details")
    row = TaskRow(controller, task)
    deselected: list[str] = []
    row.row_deselected.connect(deselected.append)
    row.set_pinned(True)
    assert not row._desc_wrap.isHidden()

    pos = row._name_label.mapTo(row, row._name_label.rect().center())
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    row.mousePressEvent(event)
    qapp.processEvents()

    assert not row._pinned
    assert row._desc_wrap.isHidden()
    assert deselected == [task.id]


def test_pinned_task_collapses_when_switching_view(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    task = controller.create_task("Only in all", description="Details")
    controller.remove_from_plan(task.id)
    main_window._set_view("all")
    main_window._on_task_row_selected(task.id)
    assert main_window._task_rows[task.id]._pinned

    main_window._set_view("plan")
    qapp.processEvents()
    assert task.id not in main_window._task_rows
    assert main_window._pinned_task_row_id is None
    assert all(not row._pinned for row in main_window._task_rows.values())

    main_window._set_view("all")
    qapp.processEvents()
    assert not main_window._task_rows[task.id]._pinned


def test_pinned_task_collapses_when_switching_to_in_progress(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    task = controller.create_task("test webdav1", description="")
    controller.stop_task(task.id)
    main_window._set_view("all")
    main_window._on_task_row_selected(task.id)
    row = main_window._task_rows[task.id]
    assert row._pinned
    assert row._actions.parentWidget() is row._pinned_footer

    main_window._set_view("in_progress")
    qapp.processEvents()

    row = main_window._task_rows[task.id]
    assert main_window._pinned_task_row_id is None
    assert not row._pinned
    assert row._actions.parentWidget() is row._header
    assert row._desc_wrap.isHidden()
    assert row.height() == 48


def test_complete_other_task_keeps_pinned_task_expanded(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    pinned = controller.create_task("Pinned task", description="")
    other = controller.create_task("Other task", description="Details")
    controller.stop_task(pinned.id)
    main_window.show()
    main_window._set_view("plan")
    main_window.refresh_ui()
    qapp.processEvents()
    main_window._on_task_row_selected(pinned.id)
    pinned_row = main_window._task_rows[pinned.id]
    assert pinned_row._pinned
    assert not pinned_row._desc_wrap.isHidden()
    assert pinned_row._actions.parentWidget() is pinned_row._pinned_footer
    assert pinned_row.height() > 48

    monkeypatch.setattr(
        "timerapp_ag.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    main_window._confirm_complete_task(other.id)
    qapp.processEvents()

    assert main_window._pinned_task_row_id == pinned.id
    restored = main_window._task_rows[pinned.id]
    assert restored._pinned
    assert not restored._desc_wrap.isHidden()
    assert restored._actions.parentWidget() is restored._pinned_footer
    assert restored._pinned_footer.isVisible()
    assert restored.height() > 48


def test_resume_other_task_keeps_pinned_task_expanded(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    pinned = controller.create_task("Pinned task", description="")
    other = controller.create_task("Other task", description="Details")
    controller.stop_task(pinned.id)
    controller.complete_task(other.id)
    main_window.show()
    main_window._set_view("plan")
    main_window.refresh_ui()
    qapp.processEvents()
    main_window._on_task_row_selected(pinned.id)
    pinned_row = main_window._task_rows[pinned.id]
    assert pinned_row._pinned

    main_window._resume_task(other.id)
    qapp.processEvents()

    assert main_window._pinned_task_row_id == pinned.id
    restored = main_window._task_rows[pinned.id]
    assert restored._pinned
    assert not restored._desc_wrap.isHidden()
    assert restored._actions.parentWidget() is restored._pinned_footer
    assert restored._pinned_footer.isVisible()
    assert restored.height() > 48


def test_complete_pinned_task_collapses_row(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    task = controller.create_task("Pinned complete", description="")
    controller.stop_task(task.id)
    main_window._set_view("plan")
    main_window.refresh_ui()
    main_window._on_task_row_selected(task.id)
    assert main_window._task_rows[task.id]._pinned

    monkeypatch.setattr(
        "timerapp_ag.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    main_window._confirm_complete_task(task.id)
    qapp.processEvents()

    row = main_window._task_rows[task.id]
    assert main_window._pinned_task_row_id is None
    assert not row._pinned
    assert row._desc_wrap.isHidden()


def test_resume_pinned_task_collapses_row(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    task = controller.create_task("Pinned resume", description="")
    controller.complete_task(task.id)
    main_window._set_view("plan")
    main_window.refresh_ui()
    main_window._on_task_row_selected(task.id)
    assert main_window._task_rows[task.id]._pinned

    main_window._resume_task(task.id)
    qapp.processEvents()

    row = main_window._task_rows[task.id]
    assert main_window._pinned_task_row_id is None
    assert not row._pinned
    assert row._desc_wrap.isHidden()


def test_refresh_ui_keeps_pinned_row_visible_after_rebuild(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = controller.create_task("Visible after refresh", description="Details")
    main_window._set_view("plan")
    main_window._on_task_row_selected(task.id)
    calls: list[str] = []

    original = main_window._restore_pinned_task_row

    def wrapped() -> None:
        calls.append("ensure")
        original()

    monkeypatch.setattr(main_window, "_restore_pinned_task_row", wrapped)
    main_window.refresh_ui()

    assert calls == ["ensure"]


def test_start_task_clears_pinned_row(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = controller.create_task("Pin and start", description="Details")
    monkeypatch.setattr(main_window, "_resolve_start_priority", lambda _task_id: 2)
    main_window._set_view("plan")
    main_window._on_task_row_selected(task.id)
    main_window._start_task(task.id)

    assert main_window._pinned_task_row_id is None
    assert not main_window._task_rows[task.id]._pinned


def test_start_task_cancelled_priority_prompt_does_not_start(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = controller.create_task("Cancel start", description="Details")
    monkeypatch.setattr(main_window, "_prompt_start_priority", lambda _task_id: None)

    main_window._start_task(task.id)

    reloaded = controller.find_task(task.id)
    assert reloaded.status == TaskStatus.OPEN
    assert reloaded.active_session() is None


def test_start_task_sets_priority_from_prompt(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = controller.create_task("Prompted start", description="Details")
    monkeypatch.setattr(main_window, "_prompt_start_priority", lambda _task_id: 2)

    main_window._start_task(task.id)

    reloaded = controller.find_task(task.id)
    assert reloaded.status == TaskStatus.RUNNING
    assert controller.task_priority(reloaded) == 2


def test_start_task_skips_prompt_when_priority_already_set(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = controller.create_task("Already prioritized", description="Details")
    controller.set_tasks_priority([task.id], 2)

    def fail_if_prompted(_task_id: str) -> int:
        raise AssertionError("priority prompt should not be shown")

    monkeypatch.setattr(main_window, "_prompt_start_priority", fail_if_prompted)

    main_window._start_task(task.id)

    reloaded = controller.find_task(task.id)
    assert reloaded.status == TaskStatus.RUNNING
    assert controller.task_priority(reloaded) == 2


def test_start_task_prompts_only_for_default_priority(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = controller.create_task("Default priority", description="Details")
    calls: list[str] = []
    monkeypatch.setattr(
        main_window,
        "_prompt_start_priority",
        lambda task_id: calls.append(task_id) or 1,
    )

    main_window._start_task(task.id)

    assert calls == [task.id]
    assert controller.find_task(task.id).status == TaskStatus.RUNNING


def test_add_to_plan_prompts_priority_and_shows_on_today_tab(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    from datetime import date, timedelta

    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Add to plan",
        planned_days=[],
    )
    controller.state.tasks.append(task)
    monkeypatch.setattr(main_window, "_prompt_plan_priority", lambda _task_id: 2)

    main_window._set_view("all")
    main_window.refresh_ui()
    main_window._add_to_plan_with_priority_prompt(task.id)
    qapp.processEvents()
    main_window._set_view("plan")
    main_window.refresh_ui()
    qapp.processEvents()

    titles = {row._title for row in main_window._task_rows.values()}
    assert "Add to plan" in titles
    assert controller.in_today_plan(controller.find_task(task.id))


def test_add_to_plan_cancelled_does_not_change_plan(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import date, timedelta

    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Cancel plan",
        planned_days=[],
    )
    controller.state.tasks.append(task)
    monkeypatch.setattr(main_window, "_prompt_plan_priority", lambda _task_id: None)

    main_window._add_to_plan_with_priority_prompt(task.id)

    reloaded = controller.find_task(task.id)
    assert not controller.in_today_plan(reloaded)
    assert today not in reloaded.planned_days


def test_remove_from_plan_cancelled_keeps_task_in_plan(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    task = controller.create_task("Stay in plan", description="")
    controller.stop_task(task.id)
    monkeypatch.setattr(
        "timerapp_ag.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    main_window._confirm_remove_from_plan(task.id)

    assert controller.in_today_plan(controller.find_task(task.id))


def test_remove_from_plan_confirmed_removes_task_from_plan(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    task = controller.create_task("Leave plan", description="")
    controller.stop_task(task.id)
    monkeypatch.setattr(
        "timerapp_ag.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    main_window._confirm_remove_from_plan(task.id)

    assert not controller.in_today_plan(controller.find_task(task.id))


def test_task_row_pinned_shows_readonly_meta_on_one_line(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(900)
    layout = QVBoxLayout(container)
    task = controller.create_task("Meta task", description="Описание")
    controller.complete_task(task.id)
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()

    meta_values = row._meta_box.findChildren(QLabel, "taskRowMetaVal")
    assert len(meta_values) == 2
    assert all(not hasattr(label, "editingFinished") for label in meta_values)
    assert meta_values[0].width() == meta_values[1].width()
    assert "Создана" in {
        child.text()
        for child in row._meta_box.findChildren(QLabel, "taskRowMetaLbl")
    }
    assert row._meta_box.parentWidget() is row._stats_row_wrap


def test_task_row_pinned_meta_wraps_on_min_list_width(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(TASK_LIST_MIN_WIDTH)
    layout = QVBoxLayout(container)
    task = controller.create_task("Meta wrap", description="Описание")
    controller.complete_task(task.id)
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()

    assert row._stats_wrap_vertical is True
    meta_pos = row._meta_box.mapTo(row, row._meta_box.rect().topLeft())
    times_pos = row._times_box.mapTo(row, row._times_box.rect().topLeft())
    assert meta_pos.y() < times_pos.y()


def test_task_row_pinned_meta_stays_horizontal_when_wide(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(900)
    layout = QVBoxLayout(container)
    task = controller.create_task("Meta wide", description="Описание")
    controller.complete_task(task.id)
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()

    assert row._stats_wrap_vertical is False
    meta_pos = row._meta_box.mapTo(row, row._meta_box.rect().topLeft())
    times_pos = row._times_box.mapTo(row, row._times_box.rect().topLeft())
    assert meta_pos.y() == times_pos.y()


def test_task_row_long_description_wraps_within_row_width(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(520)
    layout = QVBoxLayout(container)
    long_desc = ("ffff " * 20).strip() + " " + ("f" * 200)
    task = controller.create_task("Wrap", description=long_desc)
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()
    max_desc_width = 520 - 40 - TASK_ROW_DESC_HORIZONTAL_INSET
    assert row.width() <= 520
    assert row._desc_label.width() <= max_desc_width + 5
    line_height = row._desc_label.fontMetrics().height()
    assert row._desc_label.height() > line_height * 2


def test_task_row_pinned_moves_actions_to_footer(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(520)
    layout = QVBoxLayout(container)
    task = controller.create_task("Actions", description="Описание")
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()
    assert row._pinned_footer.isVisible()
    assert row._actions.parentWidget() is row._pinned_footer
    assert row._actions.isEnabled()
    assert not row._actions_fade.isVisible()


def test_task_row_pinned_start_button_centered_in_footer(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(520)
    layout = QVBoxLayout(container)
    task = controller.create_task("Лаб Правосудия", description="Описание задачи")
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()

    start_button = next(
        child
        for child in row._actions.findChildren(QWidget)
        if child.objectName() == "rowStart"
    )
    footer = row._pinned_footer
    start_center_y = start_button.mapTo(footer, start_button.rect().center()).y()
    footer_center_y = footer.height() / 2
    assert abs(start_center_y - footer_center_y) <= 1.5
    margins = row._pinned_footer_layout.contentsMargins()
    assert margins.top() == TASK_ROW_PINNED_FOOTER_V_PAD
    assert margins.bottom() == TASK_ROW_PINNED_FOOTER_V_PAD


def test_main_window_minimum_width_protects_subbar(main_window: MainWindow) -> None:
    expected = SIDEBAR_WIDTH + RIGHT_COLUMN_WIDTH + TASK_LIST_MIN_WIDTH
    assert main_window.minimumWidth() >= expected
    for button in (
        *main_window._view_buttons.values(),
        main_window._portal_button,
        main_window._add_task_button,
    ):
        assert button.width() >= button.fontMetrics().horizontalAdvance(button.text())
    label = main_window.today_total_label
    assert label.width() >= label.fontMetrics().horizontalAdvance(label.text())


def test_summary_label_uses_fixed_sample_width(main_window: MainWindow) -> None:
    metrics = main_window.today_total_label.fontMetrics()
    expected = metrics.horizontalAdvance(SUMMARY_LABEL_SAMPLE) + 12
    assert main_window.today_total_label.width() >= expected


def test_task_row_unpinned_name_has_minimum_width(
    qapp: QApplication, controller: AppController
) -> None:
    task = controller.create_task("СИНай: подумать над промтом")
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(800)
    layout = QVBoxLayout(container)
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    qapp.processEvents()
    assert row._name_label.minimumWidth() == TASK_ROW_NAME_MIN_WIDTH
    assert len(row._name_label.text()) > 5


def test_task_row_pinned_long_title_wraps(
    qapp: QApplication, controller: AppController
) -> None:
    title = "СИНай: " + ("оченьдлинноеслово " * 8).strip()
    task = controller.create_task(title, description="Кратко")
    row = TaskRow(controller, task)
    row.resize(520, 400)
    row.set_pinned(True)
    qapp.processEvents()
    line_height = row._name_label.fontMetrics().height()
    assert row._name_label.height() > line_height
    assert "СИНай" in row._name_label.text()


def test_task_row_pinned_long_title_wraps_meta_vertically(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(700)
    layout = QVBoxLayout(container)
    title = "По реестрам: обсудили с Аней и ещё немного текста для переноса"
    task = controller.create_task(title, description="")
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()

    assert row._stats_wrap_vertical is True
    meta_pos = row._meta_box.mapTo(row, row._meta_box.rect().topLeft())
    times_pos = row._times_box.mapTo(row, row._times_box.rect().topLeft())
    assert meta_pos.y() < times_pos.y()


def test_task_row_pinned_description_above_actions(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(520)
    layout = QVBoxLayout(container)
    task = controller.create_task("Actions order", description="Описание")
    row = TaskRow(controller, task)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()

    desc_pos = row._desc_wrap.mapTo(row, row._desc_wrap.rect().topLeft())
    footer_pos = row._pinned_footer.mapTo(row, row._pinned_footer.rect().topLeft())
    assert desc_pos.y() < footer_pos.y()


def test_priority_bar_visible_only_on_plan_view(
    main_window: MainWindow,
) -> None:
    main_window._set_view("plan")
    assert not main_window._priority_bar.isHidden()
    main_window._set_view("in_progress")
    assert not main_window._priority_bar.isHidden()
    main_window._set_view("all")
    assert not main_window._priority_bar.isHidden()
    main_window._set_view("date")
    assert main_window._priority_bar.isHidden()


def test_priority_filter_hides_tasks_by_level(
    main_window: MainWindow,
    controller: AppController,
) -> None:
    high = controller.create_task("High priority")
    low = controller.create_task("Low priority")
    controller.set_tasks_priority([high.id], 1)
    controller.set_tasks_priority([low.id], 4)
    controller.set_priority_filter_levels({1})
    main_window._set_view("plan")
    titles = {controller.find_task(task_id).title for task_id in main_window._task_rows}
    assert titles == {"High priority"}


def test_priority_filter_hides_tasks_by_level_in_all_view(
    main_window: MainWindow,
    controller: AppController,
) -> None:
    high = controller.create_task("High all")
    low = controller.create_task("Low all")
    controller.set_tasks_priority([high.id], 1)
    controller.set_tasks_priority([low.id], 4)
    controller.set_priority_filter_levels({1})

    main_window._set_view("all")

    titles = {controller.find_task(task_id).title for task_id in main_window._task_rows}
    assert titles == {"High all"}


def test_priority_filter_hides_tasks_by_level_in_in_progress_view(
    main_window: MainWindow,
    controller: AppController,
) -> None:
    high = controller.create_task("High progress")
    low = controller.create_task("Low progress")
    controller.set_tasks_priority([high.id], 1)
    controller.set_tasks_priority([low.id], 4)
    controller.set_priority_filter_levels({1})

    main_window._set_view("in_progress")

    titles = {controller.find_task(task_id).title for task_id in main_window._task_rows}
    assert titles == {"High progress"}


def test_priority_filter_clears_pinned_task(
    main_window: MainWindow,
    controller: AppController,
) -> None:
    task = controller.create_task("Pinned filter target", description="Details")
    main_window._set_view("plan")
    main_window._on_task_row_selected(task.id)

    assert main_window._pinned_task_row_id == task.id
    assert main_window._task_rows[task.id]._pinned

    main_window._toggle_priority_filter(4)

    assert main_window._pinned_task_row_id is None
    assert all(not row._pinned for row in main_window._task_rows.values())


def test_priority_bar_shows_hidden_selected_count(
    main_window: MainWindow,
    controller: AppController,
) -> None:
    high = controller.create_task("Visible selected")
    hidden = controller.create_task("Hidden selected")
    controller.set_tasks_priority([high.id], 1)
    controller.set_tasks_priority([hidden.id], 4)
    main_window._set_view("plan")
    main_window._on_task_row_selection_changed(high.id, True)
    main_window._on_task_row_selection_changed(hidden.id, True)

    main_window._toggle_priority_filter(4)

    assert hidden.id not in main_window._task_rows
    assert not main_window._priority_hidden_selection_label.isHidden()
    assert "1" in main_window._priority_hidden_selection_label.text()


def test_apply_priority_updates_selected_rows(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    task = controller.create_task("Apply priority")
    main_window._set_view("plan")
    row = main_window._task_rows[task.id]
    row.set_row_checked(True)
    main_window._on_task_row_selection_changed(task.id, True)
    main_window._apply_priority_to_selection(2)
    qapp.processEvents()
    assert controller.task_priority(task) == 2
    row = main_window._task_rows[task.id]
    assert row._priority_badge.text() == "2"
    assert row._priority_badge.property("priority") == "2"


def test_apply_priority_four_assigns_explicit_low_priority(
    main_window: MainWindow,
    controller: AppController,
    qapp: QApplication,
) -> None:
    from datetime import date, timedelta

    today = controller.today_str()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = Task(
        id=make_id(),
        day=yesterday,
        title="Bulk four",
        planned_days=[],
    )
    controller.state.tasks.append(task)
    main_window._set_view("all")
    qapp.processEvents()
    main_window._selected_task_ids.add(task.id)

    main_window._apply_priority_to_selection(4)
    qapp.processEvents()

    stored = controller.find_task(task.id)
    assert stored.daily_priorities[today] == 4
    assert today in stored.planned_days
    assert stored.title in {item.title for item in controller.tasks_today_plan(today)}


def test_create_task_start_now_skips_priority_prompt(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_prompted(_task_id: str) -> int:
        raise AssertionError("priority prompt should not be shown")

    monkeypatch.setattr(main_window, "_prompt_start_priority", fail_if_prompted)

    main_window._create_task(
        {
            "title": "Immediate",
            "description": "",
            "priority": 2,
            "start_now": True,
        }
    )

    task = next(item for item in controller.state.tasks if item.title == "Immediate")
    assert task.status == TaskStatus.RUNNING
    assert controller.task_priority(task) == 2


def test_focus_resume_skips_priority_prompt(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    task = controller.create_task("Focus resume", description="")
    controller.assign_tasks_priority([task.id], 2)
    controller.start_task(task.id)
    controller.start_focus_timer(10)

    def fail_if_prompted(_task_id: str) -> int:
        raise AssertionError("priority prompt should not be shown")

    monkeypatch.setattr(main_window, "_prompt_start_priority", fail_if_prompted)
    monkeypatch.setattr(
        "timerapp_ag.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    main_window._prompt_focus_resume(task.id)

    reloaded = controller.find_task(task.id)
    assert reloaded.status == TaskStatus.RUNNING
    assert controller.task_priority(reloaded) == 2


def test_task_row_checkbox_does_not_pin_row(
    qapp: QApplication,
    controller: AppController,
) -> None:
    task = controller.create_task("Checkbox row")
    row = TaskRow(controller, task, plan_mode=True)
    row.resize(520, 120)
    row.show()
    qapp.processEvents()

    row._select_checkbox.click()
    qapp.processEvents()

    assert not row._pinned
    assert row._select_checkbox.isChecked()


def test_task_row_plan_mode_long_title_wraps_meta_vertically(
    qapp: QApplication, controller: AppController
) -> None:
    container = QWidget()
    container.setObjectName("taskListBg")
    container.setFixedWidth(700)
    layout = QVBoxLayout(container)
    title = "Альфаро Про: внести изменение в бизнес-процесс и ещё длинный хвост для переноса"
    task = controller.create_task(title, description="Описание")
    row = TaskRow(controller, task, plan_mode=True)
    layout.addWidget(row)
    container.show()
    row.set_pinned(True)
    qapp.processEvents()

    assert row._stats_wrap_vertical is True
    meta_pos = row._meta_box.mapTo(row, row._meta_box.rect().topLeft())
    times_pos = row._times_box.mapTo(row, row._times_box.rect().topLeft())
    assert meta_pos.y() < times_pos.y()


def test_plan_view_sorts_tasks_by_priority(
    main_window: MainWindow,
    controller: AppController,
) -> None:
    high = controller.create_task("High first")
    low = controller.create_task("Low second")
    controller.set_tasks_priority([high.id], 1)
    controller.set_priority_filter_levels({1, 2, 3, 4})
    main_window._set_view("plan")
    titles = [controller.find_task(task_id).title for task_id in main_window._task_rows]
    assert titles.index("High first") < titles.index("Low second")


def test_break_long_unbroken_runs_inserts_zero_width_spaces() -> None:
    broken = break_long_unbroken_runs("abcdefgh", max_run=3)
    assert broken == "abc\u200bdef\u200bgh"


def test_update_task_row_times_called_from_tick(
    main_window: MainWindow, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller.create_task("Live", start_now=True)
    main_window.refresh_ui()
    calls: list[int] = []
    monkeypatch.setattr(
        main_window,
        "_update_task_row_times",
        lambda: calls.append(1),
    )
    main_window._tick()
    assert calls == [1]


def test_floating_shows_focus_mode(
    main_window: MainWindow, controller: AppController
) -> None:
    main_window._start_focus_timer(20)
    assert main_window.floating.isVisible()
    assert "Концентрация" in main_window.floating.name_label.text()
    assert main_window.floating.time_label.text().startswith("00:")
    assert main_window.floating.stop_button.isEnabled()
    assert not main_window.floating.start_button.isEnabled()


def test_floating_stop_ends_focus_mode(
    main_window: MainWindow, controller: AppController
) -> None:
    main_window._start_focus_timer(20)
    assert controller.focus_remaining_seconds() > 0
    main_window._floating_stop()
    assert controller.focus_remaining_seconds() == 0
    assert controller.check_focus_timer()[0] == "idle"


def test_manual_stop_focus_offers_resume(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    task = controller.create_task("Work", start_now=True)
    controller.start_focus_timer(10)
    prompts: list[tuple[object, ...]] = []

    def _question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        prompts.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr("timerapp_ag.main_window.QMessageBox.question", _question)
    main_window._stop_focus_timer()
    assert prompts
    assert task.title in str(prompts[0])


def test_stop_focus_timer_clears_pinned_row(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtWidgets import QMessageBox

    task = controller.create_task("Pinned focus target", description="Details", start_now=True)
    main_window._set_view("plan")
    main_window._on_task_row_selected(task.id)
    controller.start_focus_timer(10)

    monkeypatch.setattr(
        "timerapp_ag.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    main_window._stop_focus_timer()

    assert main_window._pinned_task_row_id is None


def test_floating_stop_clears_pinned_row(
    main_window: MainWindow,
    controller: AppController,
) -> None:
    task = controller.create_task("Floating stop target", description="Details", start_now=True)
    main_window._set_view("plan")
    main_window._on_task_row_selected(task.id)
    main_window._floating_stop()

    assert main_window._pinned_task_row_id is None


def test_tick_focus_finish_prompts_resume(
    main_window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timedelta

    from PySide6.QtWidgets import QMessageBox

    task = controller.create_task("Work", start_now=True)
    controller.start_focus_timer(10)
    controller.state.ui["focus_timer"]["ends_at"] = (
        datetime.now() - timedelta(seconds=1)
    ).isoformat()
    prompts: list[tuple[object, ...]] = []

    def _question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        prompts.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr("timerapp_ag.main_window.QMessageBox.question", _question)
    monkeypatch.setattr("timerapp_ag.main_window.QApplication.beep", lambda: None)
    monkeypatch.setattr(main_window, "_show_tray_message", lambda *args, **kwargs: None)

    main_window._tick()

    assert prompts
    assert "Work" in str(prompts[0])
    assert controller.focus_paused_task_id is None


def test_floating_close_hides_widget_until_tray_show(
    main_window: MainWindow, controller: AppController
) -> None:
    task = controller.create_task("Tray task", start_now=True)
    main_window._track_floating_task(task.id)
    main_window._show_floating()
    assert main_window.floating.isVisible()

    main_window._floating_close()
    assert not main_window.floating.isVisible()
    assert main_window._floating_user_dismissed

    main_window._show_floating()
    assert not main_window.floating.isVisible()

    main_window._show_floating_from_tray()
    assert main_window.floating.isVisible()
    assert not main_window._floating_user_dismissed


def test_settings_dialog_bitrix_fields_keep_min_height(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_FIELD_MIN_HEIGHT, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.resize(620, 540)
    dialog.show()
    qapp.processEvents()

    for field in (
        dialog.reminder_spin,
        dialog.webhook_edit,
        dialog.registry_title_edit,
        dialog.entity_type_spin,
        dialog.executor_fields_edit,
    ):
        assert field.height() >= SETTINGS_FIELD_MIN_HEIGHT


def test_settings_dialog_enforces_minimum_window_size(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import (
        SETTINGS_DIALOG_MIN_HEIGHT,
        SETTINGS_DIALOG_MIN_WIDTH,
        SettingsDialog,
    )

    dialog = SettingsDialog(controller)
    assert dialog.minimumWidth() == SETTINGS_DIALOG_MIN_WIDTH
    assert dialog.minimumHeight() >= SETTINGS_DIALOG_MIN_HEIGHT

    dialog.resize(120, 100)
    dialog.show()
    qapp.processEvents()

    assert dialog.width() >= SETTINGS_DIALOG_MIN_WIDTH
    assert dialog.height() >= dialog.minimumHeight()


def test_settings_dialog_action_buttons_visible_at_minimum_width(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_MIN_WIDTH, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()
    dialog.resize(SETTINGS_DIALOG_MIN_WIDTH, dialog.height())
    qapp.processEvents()

    margin = 4
    tabs = _settings_dialog_tabs(dialog)

    tabs.setCurrentIndex(0)
    qapp.processEvents()
    for button in (dialog.test_button, dialog.discover_button):
        assert button.isVisibleTo(dialog)
        assert _widget_right_in_ancestor(button, dialog) <= dialog.width() - margin
        assert button.mapTo(dialog, button.rect().topLeft()).x() >= margin

    tabs.setCurrentIndex(1)
    qapp.processEvents()
    for button in (
        dialog.webdav_test_button,
        dialog.webdav_pull_button,
        dialog.webdav_push_button,
    ):
        assert button.isVisibleTo(dialog)
        assert _widget_right_in_ancestor(button, dialog) <= dialog.width() - margin
        assert button.mapTo(dialog, button.rect().topLeft()).x() >= margin

    for index in (0, 1):
        tabs.setCurrentIndex(index)
        qapp.processEvents()
        scroll = tabs.widget(index)
        assert isinstance(scroll, QScrollArea)
        _assert_settings_tab_fits_or_scrolls(scroll)


def test_settings_dialog_min_height_grows_when_narrowing(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_MIN_WIDTH, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()
    dialog.resize(620, dialog.minimumHeight())
    qapp.processEvents()
    wide_min_height = dialog.minimumHeight()

    dialog.resize(SETTINGS_DIALOG_MIN_WIDTH, dialog.height())
    qapp.processEvents()

    assert dialog.minimumHeight() >= wide_min_height


def test_settings_dialog_long_status_updates_layout_at_minimum_width(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_MIN_WIDTH, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()
    dialog.resize(SETTINGS_DIALOG_MIN_WIDTH, dialog.height())
    qapp.processEvents()

    tabs = _settings_dialog_tabs(dialog)
    tabs.setCurrentIndex(0)
    qapp.processEvents()
    scroll = tabs.widget(0)
    assert isinstance(scroll, QScrollArea)
    inner = scroll.widget()
    assert inner is not None
    baseline_height = inner.minimumHeight()

    long_status = "✗ " + ("Очень длинное сообщение об ошибке подключения. " * 8)
    dialog._set_status(long_status, ok=False)
    qapp.processEvents()

    assert inner.minimumHeight() >= baseline_height
    _assert_settings_tab_fits_or_scrolls(scroll)


def test_settings_dialog_webdav_sync_finished_refits_persisted_status(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    controller: AppController,
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_MIN_WIDTH, SettingsDialog
    from timerapp_ag.webdav_config import WebDavConfig

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()
    dialog.resize(SETTINGS_DIALOG_MIN_WIDTH, dialog.height())
    qapp.processEvents()

    tabs = _settings_dialog_tabs(dialog)
    tabs.setCurrentIndex(1)
    qapp.processEvents()
    scroll = tabs.widget(1)
    assert isinstance(scroll, QScrollArea)
    inner = scroll.widget()
    assert inner is not None

    dialog._set_webdav_status("Скачиваю и объединяю…", ok=None)
    qapp.processEvents()
    short_height = inner.minimumHeight()

    long_error = "Ошибка синхронизации WebDAV. " * 12
    persisted = WebDavConfig(
        last_sync_at="2026-06-21T12:00:00",
        last_error=long_error,
    )
    monkeypatch.setattr(
        "timerapp_ag.main_window.load_webdav_config",
        lambda: persisted,
    )

    dialog._on_webdav_sync_finished()
    qapp.processEvents()

    assert dialog.webdav_status.text() == dialog._webdav_status_text(persisted)
    assert inner.minimumHeight() >= short_height
    assert "#9b3c3c" in dialog.webdav_status.styleSheet()
    _assert_settings_tab_fits_or_scrolls(scroll)


def test_settings_dialog_caps_height_on_small_screen(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    controller: AppController,
) -> None:
    from unittest.mock import MagicMock

    from timerapp_ag.main_window import (
        SETTINGS_DIALOG_MIN_WIDTH,
        SettingsDialog,
    )

    fake_screen = MagicMock()
    fake_screen.availableGeometry.return_value = QRect(0, 0, 800, 580)

    dialog = SettingsDialog(controller)
    monkeypatch.setattr(dialog, "screen", lambda: fake_screen)
    dialog.show()
    qapp.processEvents()

    assert dialog.minimumHeight() <= 580
    assert dialog.width() >= SETTINGS_DIALOG_MIN_WIDTH

    tabs = _settings_dialog_tabs(dialog)
    for index in (0, 1):
        tabs.setCurrentIndex(index)
        qapp.processEvents()
        scroll = tabs.widget(index)
        assert isinstance(scroll, QScrollArea)
        _assert_settings_tab_fits_or_scrolls(scroll)


def test_settings_dialog_caps_height_on_very_short_screen(
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    controller: AppController,
) -> None:
    from unittest.mock import MagicMock

    from timerapp_ag.main_window import SETTINGS_DIALOG_MIN_WIDTH, SettingsDialog

    fake_screen = MagicMock()
    fake_screen.availableGeometry.return_value = QRect(0, 0, 800, 480)

    dialog = SettingsDialog(controller)
    monkeypatch.setattr(dialog, "screen", lambda: fake_screen)
    dialog.show()
    qapp.processEvents()

    assert dialog.minimumHeight() <= 480
    assert dialog.width() >= SETTINGS_DIALOG_MIN_WIDTH

    tabs = _settings_dialog_tabs(dialog)
    for index in (0, 1):
        tabs.setCurrentIndex(index)
        qapp.processEvents()
        scroll = tabs.widget(index)
        assert isinstance(scroll, QScrollArea)
        _assert_settings_tab_fits_or_scrolls(scroll)


def test_settings_dialog_form_fields_visible_at_minimum_width(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_MIN_WIDTH, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()
    dialog.resize(SETTINGS_DIALOG_MIN_WIDTH, dialog.height())
    qapp.processEvents()

    tabs = _settings_dialog_tabs(dialog)
    tabs.setCurrentIndex(0)
    qapp.processEvents()

    margin = 4
    for field in (
        dialog.webhook_edit,
        dialog.entity_type_spin,
        dialog.executor_fields_edit,
    ):
        assert field.isVisibleTo(dialog)
        assert _widget_right_in_ancestor(field, dialog) <= dialog.width() - margin
        assert field.mapTo(dialog, field.rect().bottomLeft()).y() <= dialog.height() - margin


def test_settings_dialog_resize_stabilizes_height(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_MIN_WIDTH, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()
    dialog.resize(SETTINGS_DIALOG_MIN_WIDTH + 40, dialog.minimumHeight())
    qapp.processEvents()
    stable_height = dialog.height()

    for _ in range(4):
        dialog.resize(SETTINGS_DIALOG_MIN_WIDTH + 40, dialog.minimumHeight())
        qapp.processEvents()
        assert dialog.height() == stable_height


def test_settings_dialog_default_height_fits_bitrix_tab(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_DEFAULT_HEIGHT, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()

    assert dialog.height() >= SETTINGS_DIALOG_DEFAULT_HEIGHT
    tabs = _settings_dialog_tabs(dialog)
    tabs.setCurrentIndex(0)
    qapp.processEvents()
    scroll = tabs.widget(0)
    assert isinstance(scroll, QScrollArea)
    inner = scroll.widget()
    assert inner is not None
    assert scroll.viewport().height() >= inner.minimumHeight()
    assert inner.height() >= inner.minimumHeight()
    assert dialog.discover_button.isVisibleTo(inner)


def test_settings_dialog_default_height_fits_webdav_tab(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SETTINGS_DIALOG_DEFAULT_HEIGHT, SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()
    tabs = _settings_dialog_tabs(dialog)
    tabs.setCurrentIndex(1)
    qapp.processEvents()

    assert dialog.height() >= SETTINGS_DIALOG_DEFAULT_HEIGHT
    scroll = tabs.widget(1)
    assert isinstance(scroll, QScrollArea)
    inner = scroll.widget()
    assert inner is not None
    assert scroll.viewport().height() >= inner.minimumHeight()
    assert inner.height() >= inner.minimumHeight()


def test_settings_dialog_chrome_height_matches_layout(
    qapp: QApplication, controller: AppController
) -> None:
    from timerapp_ag.main_window import SettingsDialog

    dialog = SettingsDialog(controller)
    dialog.show()
    qapp.processEvents()

    tabs = _settings_dialog_tabs(dialog)
    scroll = tabs.currentWidget()
    assert isinstance(scroll, QScrollArea)
    measured_chrome = dialog.height() - scroll.height()
    assert measured_chrome > 0
    assert abs(dialog._settings_dialog_chrome_height() - measured_chrome) <= 8
