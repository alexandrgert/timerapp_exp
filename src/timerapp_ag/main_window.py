from __future__ import annotations

import sys
import time
from datetime import datetime

from PySide6.QtCore import (
    QDate,
    QDateTime,
    QEvent,
    QStringListModel,
    QThread,
    QTimer,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .bitrix import Bitrix24Client, looks_like_webhook, seconds_to_worklog_hours
from .ui.tray_icon import (
    build_tray_app_icon,
    clear_tray_app_icon_cache,
    install_tray_icon_theme_refresh,
)
from .bitrix_config import BitrixPortalConfig
from .bitrix_transfer_journal import record_transfer_result
from .app_info import APP_TITLE_BASE, resolve_app_title
from .controller import AppController, format_day_label, format_duration, format_hm
from .models import Task, TaskStatus
from .runtime_info import build_about_report
from .webdav_config import (
    REMIND_LATER_MINUTES_CHOICES,
    WebDavConfig,
    clear_pending_remote_remind,
    clear_webdav_pending_notice,
    load_webdav_config,
    prepare_remote_prompt,
    save_pending_remote_remind,
    should_show_remote_prompt,
)
from .ui.floating_timer import FloatingTimer
from .ui.floating_view import FloatingView, resolve_floating_task, resolve_floating_view
from .ui.task_row import TaskRow
from .ui.text_layout import (
    TASK_ROW_ACTIONS_OVERLAY_RESERVE,
    TASK_ROW_DESC_HORIZONTAL_INSET,
    TASK_ROW_NAME_MIN_WIDTH,
    TASK_ROW_PINNED_FOOTER_V_PAD,
    break_long_unbroken_runs,
    fit_plain_text_edit_height,
    fit_wrapped_label_height,
    wrapped_text_height,
)
from .webdav_sync import (
    RemoteCheckOutcome,
    SyncOutcome,
    check_remote_changes,
    pull_and_merge,
    push_local,
    save_webdav_settings,
    test_webdav_connection,
)

_TRAY_TOOLTIP_FLOATING_AUTO = object()
TRAY_ACTIVATION_DEBOUNCE_SECONDS = 0.35
SIDEBAR_WIDTH = 52
RIGHT_COLUMN_WIDTH = 268
TASK_LIST_MIN_WIDTH = 600
WINDOW_MIN_HEIGHT = 680
WINDOW_VERTICAL_CHROME = 40
SUMMARY_LABEL_SAMPLE = "За 31.12.2026 всего: 00:00"
ADD_TASK_BUTTON_EXTRA_WIDTH = 16
TIMER_DIGITS_FONT_SIZE = 38
TIMER_DIGITS_VERTICAL_PAD = 6
TIMER_CARD_HORIZONTAL_INSET = 28
TIMER_CARD_STATS_SPACING = 14
SETTINGS_FIELD_MIN_HEIGHT = 36
SETTINGS_DIALOG_MIN_WIDTH = 520
SETTINGS_DIALOG_MIN_HEIGHT = 520
SETTINGS_DIALOG_DEFAULT_WIDTH = 620
SETTINGS_DIALOG_DEFAULT_HEIGHT = 860
SETTINGS_DIALOG_CHROME_HEIGHT = 132
SETTINGS_DIALOG_SCREEN_HEIGHT_RATIO = 0.92
SETTINGS_DIALOG_HORIZONTAL_INSET = 44
SETTINGS_CHECKBOX_INDICATOR_WIDTH = 28
SETTINGS_TAB_CONTENT_WIDTH = SETTINGS_DIALOG_DEFAULT_WIDTH - SETTINGS_DIALOG_HORIZONTAL_INSET
SETTINGS_TAB_SCROLL_MIN_HEIGHT = 340
FOCUS_PRESET_BUTTON_HEIGHT = 36
FOCUS_PRESET_ROW_SPACING = 5


def _configure_settings_form_field(field: QLineEdit | QSpinBox) -> None:
    field.setMinimumHeight(SETTINGS_FIELD_MIN_HEIGHT)
    field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def _configure_settings_action_button(button: QPushButton) -> None:
    button.setMinimumHeight(32)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def _configure_settings_form_layout(form: QFormLayout) -> None:
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


def _wrap_settings_tab(tab: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setMinimumHeight(SETTINGS_TAB_SCROLL_MIN_HEIGHT)
    scroll.setWidget(tab)
    return scroll


def _fit_settings_hint_label(label: QLabel, width: int = SETTINGS_TAB_CONTENT_WIDTH) -> None:
    if not label.text().strip():
        label.setFixedHeight(0)
        return
    label.setMaximumHeight(16777215)
    fit_wrapped_label_height(label, label.text(), width=width)


def _configure_settings_status_label(label: QLabel) -> None:
    label.setWordWrap(True)
    if not label.text().strip():
        label.setFixedHeight(0)


def _configure_settings_checkbox(checkbox: QCheckBox) -> None:
    checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)


def _settings_checkbox_height(checkbox: QCheckBox, content_width: int) -> int:
    text_width = max(content_width - SETTINGS_CHECKBOX_INDICATOR_WIDTH, 40)
    text_height = wrapped_text_height(checkbox.text(), width=text_width, font=checkbox.font())
    return max(checkbox.sizeHint().height(), text_height + 4)


def _prepare_settings_widget_for_measure(widget: QWidget, content_width: int) -> None:
    if isinstance(widget, QLabel) and widget.wordWrap():
        _fit_settings_hint_label(widget, content_width)
    elif isinstance(widget, QCheckBox):
        widget.setMinimumHeight(_settings_checkbox_height(widget, content_width))
    child_layout = widget.layout()
    if child_layout is not None:
        _prepare_settings_layout_for_measure(child_layout, content_width)


def _prepare_settings_layout_for_measure(
    layout: QFormLayout | QHBoxLayout | QVBoxLayout,
    content_width: int,
) -> None:
    if isinstance(layout, QFormLayout):
        for row in range(layout.rowCount()):
            for role in (QFormLayout.ItemRole.LabelRole, QFormLayout.ItemRole.FieldRole):
                item = layout.itemAt(row, role)
                if item is None or item.widget() is None:
                    continue
                _prepare_settings_widget_for_measure(item.widget(), content_width)
        return
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is not None:
            _prepare_settings_widget_for_measure(item.widget(), content_width)
        elif item.layout() is not None:
            _prepare_settings_layout_for_measure(item.layout(), content_width)


def _prepare_settings_tab_for_measure(inner: QWidget, content_width: int) -> None:
    inner.setMinimumWidth(content_width)
    inner.setMaximumWidth(content_width)
    root_layout = inner.layout()
    if root_layout is not None:
        _prepare_settings_layout_for_measure(root_layout, content_width)


def _settings_form_layout_height(form: QFormLayout) -> int:
    hinted = form.sizeHint().height()
    if hinted > 0:
        return hinted
    if form.rowCount() == 0:
        return 0
    height = form.contentsMargins().top() + form.contentsMargins().bottom()
    for row in range(form.rowCount()):
        row_height = 0
        has_field = False
        for role in (QFormLayout.ItemRole.LabelRole, QFormLayout.ItemRole.FieldRole):
            item = form.itemAt(row, role)
            if item is None or item.widget() is None:
                continue
            if role == QFormLayout.ItemRole.FieldRole:
                has_field = True
            row_height = max(row_height, item.widget().sizeHint().height())
        if has_field:
            row_height = max(row_height, SETTINGS_FIELD_MIN_HEIGHT)
        height += row_height
        if row < form.rowCount() - 1:
            height += form.spacing()
    return height


def _settings_box_layout_height(box: QHBoxLayout | QVBoxLayout) -> int:
    height = box.contentsMargins().top() + box.contentsMargins().bottom()
    item_height = 0
    for index in range(box.count()):
        item = box.itemAt(index)
        if item.widget() is not None:
            item_height = max(item_height, item.widget().sizeHint().height())
        elif item.layout() is not None:
            item_height = max(item_height, _settings_layout_total_height(item.layout()))
    return height + item_height


def _settings_layout_total_height(
    layout: QFormLayout | QHBoxLayout | QVBoxLayout,
) -> int:
    if isinstance(layout, QFormLayout):
        return _settings_form_layout_height(layout)
    if isinstance(layout, QHBoxLayout):
        return _settings_box_layout_height(layout)
    height = layout.contentsMargins().top() + layout.contentsMargins().bottom()
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.spacerItem() is not None:
            continue
        if item.widget() is not None:
            height += item.widget().sizeHint().height()
        elif item.layout() is not None:
            height += _settings_layout_total_height(item.layout())
        if index < layout.count() - 1:
            height += layout.spacing()
    return height


def _settings_dialog_content_width(dialog_width: int) -> int:
    return max(
        dialog_width - SETTINGS_DIALOG_HORIZONTAL_INSET,
        SETTINGS_DIALOG_MIN_WIDTH - SETTINGS_DIALOG_HORIZONTAL_INSET,
    )


def _settings_tab_content_width(
    scroll: QScrollArea,
    *,
    dialog_width: int | None = None,
) -> int:
    viewport_width = scroll.viewport().width()
    if viewport_width > 0:
        return viewport_width
    if dialog_width is not None and dialog_width > 0:
        return _settings_dialog_content_width(dialog_width)
    return SETTINGS_TAB_CONTENT_WIDTH


def _measure_settings_tab_content_height(scroll: QScrollArea, content_width: int) -> int:
    inner = scroll.widget()
    if inner is None:
        return 0
    layout = inner.layout()
    if layout is None:
        return inner.sizeHint().height()
    _prepare_settings_tab_for_measure(inner, content_width)
    layout.invalidate()
    layout.activate()
    layout_hint = layout.sizeHint().height()
    height_for_width = inner.heightForWidth(content_width)
    measured = _settings_layout_total_height(layout)
    height = max(measured, layout_hint)
    if height_for_width > 0:
        height = max(height, height_for_width)
    inner.setMinimumHeight(height)
    inner.setMaximumWidth(16777215)
    inner.setMinimumWidth(0)
    return height


def format_tray_tooltip(
    *,
    window_visible: bool,
    app_title: str,
    task_titles: list[str],
) -> str:
    """Tray hover text: app name when the window is open, one line per task when hidden."""
    if window_visible:
        return app_title
    if task_titles:
        return "\n".join(task_titles)
    return "Нет активных таймеров"


def tray_tooltip_task_titles(
    *,
    running_task_titles: list[str],
    floating_task: Task | None,
    focus_line: str | None = None,
) -> list[str]:
    """Running tasks, active focus, and paused mini-widget task (without duplicates)."""
    titles = list(running_task_titles)
    if focus_line and focus_line not in titles:
        titles.insert(0, focus_line)
    if floating_task is not None and floating_task.title not in titles:
        titles.append(floating_task.title)
    return titles


def main_window_is_open(*, is_visible: bool, is_minimized: bool) -> bool:
    return is_visible and not is_minimized


def tray_activation_is_debounced(
    *,
    now: float,
    last_at: float,
    debounce_seconds: float = TRAY_ACTIVATION_DEBOUNCE_SECONDS,
) -> bool:
    return last_at > 0.0 and (now - last_at) < debounce_seconds


def bitrix_client(controller: AppController, webhook: str | None = None) -> Bitrix24Client:
    url = (webhook or controller.bitrix_webhook()).strip()
    return Bitrix24Client(url, portal_config=controller.bitrix_portal_config())


class CreateTaskCard(QFrame):
    create_requested = Signal(str, str, bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("createCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Новая задача")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Название задачи")
        layout.addWidget(self.title_edit)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Краткое описание (необязательно)")
        self.description_edit.setFixedHeight(76)
        layout.addWidget(self.description_edit)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        create_button = QPushButton("Добавить")
        create_button.clicked.connect(lambda: self._emit_request(False))
        buttons.addWidget(create_button)

        quick_start_button = QPushButton("Добавить и старт")
        quick_start_button.setObjectName("primaryButton")
        quick_start_button.clicked.connect(lambda: self._emit_request(True))
        buttons.addWidget(quick_start_button)

        layout.addLayout(buttons)

    def _emit_request(self, start_now: bool) -> None:
        title = self.title_edit.text().strip()
        description = self.description_edit.toPlainText().strip()
        if not title:
            self.title_edit.setFocus()
            return
        self.create_requested.emit(title, description, start_now)
        self.title_edit.clear()
        self.description_edit.clear()


class CreateTaskDialog(QDialog):
    create_requested = Signal(dict)

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Новая задача")
        self.setModal(True)
        self.resize(460, 380)
        self._company_id: str | None = None
        self._company_by_title: dict[str, str] = {}
        self._company_thread: _CallableThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Новая задача")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Название задачи")
        layout.addWidget(self.title_edit)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Краткое описание (необязательно)")
        self.description_edit.setFixedHeight(90)
        layout.addWidget(self.description_edit)

        self.portal_checkbox = QCheckBox("Создать задачу в Битрикс24")
        self.portal_checkbox.toggled.connect(self._toggle_portal)
        layout.addWidget(self.portal_checkbox)

        self.company_edit = QLineEdit()
        self.company_edit.setPlaceholderText("Компания (поиск от 3 символов)")
        self.company_edit.setEnabled(False)
        self._company_model = QStringListModel(self)
        completer = QCompleter(self)
        completer.setModel(self._company_model)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated[str].connect(self._on_company_selected)
        self.company_edit.setCompleter(completer)
        self.company_edit.textEdited.connect(self._on_company_text)
        layout.addWidget(self.company_edit)

        self._company_timer = QTimer(self)
        self._company_timer.setSingleShot(True)
        self._company_timer.setInterval(300)
        self._company_timer.timeout.connect(self._run_company_search)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        create_button = QPushButton("Добавить")
        create_button.clicked.connect(lambda: self._emit_request(False))
        buttons.addWidget(create_button)

        quick_start_button = QPushButton("Добавить и старт")
        quick_start_button.setObjectName("primaryButton")
        quick_start_button.clicked.connect(lambda: self._emit_request(True))
        buttons.addWidget(quick_start_button)

        layout.addLayout(buttons)

    def open_clean(self) -> None:
        self.title_edit.clear()
        self.description_edit.clear()
        self.portal_checkbox.setChecked(False)
        self.company_edit.clear()
        self._company_id = None
        self._company_by_title = {}
        self.show()
        self.raise_()
        self.activateWindow()
        self.title_edit.setFocus()

    def _toggle_portal(self, checked: bool) -> None:
        self.company_edit.setEnabled(checked)
        if not checked:
            self.company_edit.clear()
            self._company_id = None

    def _on_company_text(self, text: str) -> None:
        self._company_id = None  # text changed by hand -> require re-pick
        if len(text.strip()) >= 3:
            self._company_timer.start()
        else:
            self._company_timer.stop()

    def _run_company_search(self) -> None:
        text = self.company_edit.text().strip()
        if len(text) < 3:
            return
        webhook = self.controller.bitrix_webhook()
        if not looks_like_webhook(webhook):
            return
        client = bitrix_client(self.controller, webhook)
        self._company_thread = _CallableThread(lambda q=text: client.search_companies(q), self)
        self._company_thread.succeeded.connect(self._on_companies)
        self._company_thread.failed.connect(lambda message: None)
        self._company_thread.start()

    def _on_companies(self, companies: object) -> None:
        companies = companies if isinstance(companies, list) else []
        self._company_by_title = {
            c["title"]: c["id"] for c in companies if isinstance(c, dict) and c.get("title")
        }
        self._company_model.setStringList(list(self._company_by_title.keys()))
        self.company_edit.completer().complete()

    def _on_company_selected(self, title: str) -> None:
        self._company_id = self._company_by_title.get(title)

    def _emit_request(self, start_now: bool) -> None:
        title = self.title_edit.text().strip()
        description = self.description_edit.toPlainText().strip()
        if not title:
            self.title_edit.setFocus()
            return
        company_id = None
        if self.portal_checkbox.isChecked():
            company_id = self._company_id or self._company_by_title.get(
                self.company_edit.text().strip()
            )
        self.create_requested.emit(
            {
                "title": title,
                "description": description,
                "start_now": start_now,
                "on_portal": self.portal_checkbox.isChecked(),
                "company_id": company_id,
            }
        )
        self.accept()


_CAL_ICON_PATH: str | None = None


def _calendar_icon_path() -> str:
    """Draw a small calendar icon to a PNG once and return its path (for QSS)."""
    global _CAL_ICON_PATH
    if _CAL_ICON_PATH:
        return _CAL_ICON_PATH
    import os
    import tempfile

    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

    path = os.path.join(tempfile.gettempdir(), "tasktimer_calendar.png")
    scale = 2
    pixmap = QPixmap(24 * scale, 24 * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)
    pen = QPen(QColor("#5f6b7c"))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawRoundedRect(QRectF(3, 5, 18, 16), 2.5, 2.5)
    painter.drawLine(QPointF(3, 9.5), QPointF(21, 9.5))
    painter.drawLine(QPointF(8, 2.5), QPointF(8, 6.5))
    painter.drawLine(QPointF(16, 2.5), QPointF(16, 6.5))
    painter.end()
    pixmap.save(path, "PNG")
    _CAL_ICON_PATH = path
    return path


def _style_calendar_field(widget) -> None:
    """Give a QDateEdit/QDateTimeEdit a calendar icon and rounded right corners."""
    name = widget.objectName() or "calendarField"
    widget.setObjectName(name)
    icon = _calendar_icon_path().replace("\\", "/")
    widget.setStyleSheet(
        f"""
        #{name} {{
            background: white;
            border: 1px solid rgba(20, 22, 27, 0.12);
            border-radius: 12px;
            padding: 6px 10px;
        }}
        #{name}::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 30px;
            border: none;
            background: transparent;
            border-top-right-radius: 12px;
            border-bottom-right-radius: 12px;
        }}
        #{name}::down-arrow {{
            image: url("{icon}");
            width: 16px;
            height: 16px;
        }}
        """
    )


_CHECK_ICON_PATH: str | None = None


def _check_icon_path() -> str:
    """Draw a white checkmark PNG once (for the QCheckBox checked indicator)."""
    global _CHECK_ICON_PATH
    if _CHECK_ICON_PATH:
        return _CHECK_ICON_PATH
    import os
    import tempfile

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

    path = os.path.join(tempfile.gettempdir(), "tasktimer_check.png")
    scale = 4
    pixmap = QPixmap(16 * scale, 16 * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(4, 8.4), QPointF(7, 11.2), QPointF(12, 5)])
    painter.end()
    pixmap.save(path, "PNG")
    _CHECK_ICON_PATH = path
    return path


class _CallableThread(QThread):
    """Runs a callable off the UI thread and reports the outcome via signals."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # surfaced to the user as a status message
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


class AboutDialog(QDialog):
    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("О программе")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(resolve_app_title())
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(
            build_about_report(
                stored_webhook=controller.bitrix_webhook(),
                data_path=controller.storage.path,
            )
        )
        details.setMinimumHeight(320)
        layout.addWidget(details)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class SettingsDialog(QDialog):
    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Настройки")
        self.resize(SETTINGS_DIALOG_DEFAULT_WIDTH, SETTINGS_DIALOG_DEFAULT_HEIGHT)
        self._test_thread: _CallableThread | None = None
        self._discover_thread: _CallableThread | None = None
        self._webdav_test_thread: _CallableThread | None = None
        self._webdav_sync_thread: _CallableThread | None = None
        portal = controller.bitrix_portal_config()
        webdav = load_webdav_config()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(0, 12, 0, 0)
        general_layout.setSpacing(12)

        hint = QLabel(
            "Через указанное время после старта таймера или после ответа «Продолжить» "
            "приложение снова спросит, продолжать ли работу над задачей."
        )
        hint.setWordWrap(True)
        general_layout.addWidget(hint)
        _fit_settings_hint_label(hint)

        form = QFormLayout()
        _configure_settings_form_layout(form)
        self.reminder_spin = QSpinBox()
        self.reminder_spin.setRange(1, 24 * 60)
        self.reminder_spin.setSuffix(" мин")
        self.reminder_spin.setValue(controller.reminder_interval_minutes())
        _configure_settings_form_field(self.reminder_spin)
        form.addRow("Интервал напоминания", self.reminder_spin)

        self.webhook_edit = QLineEdit()
        self.webhook_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.webhook_edit.setPlaceholderText("https://портал.bitrix24.ru/rest/1/токен/")
        self.webhook_edit.setText(controller.bitrix_webhook())
        _configure_settings_form_field(self.webhook_edit)
        form.addRow("URL вебхука Битрикс24", self.webhook_edit)

        webhook_hint = QLabel(
            "Вебхук хранится локально в ~/.config/tasktimer/bitrix.json и не попадает в облако при WebDAV-синхронизации."
        )
        webhook_hint.setWordWrap(True)
        general_layout.addWidget(webhook_hint)
        _fit_settings_hint_label(webhook_hint)
        general_layout.addLayout(form)

        self.show_webhook_checkbox = QCheckBox("Показать")
        self.show_webhook_checkbox.toggled.connect(self._toggle_webhook_echo)
        general_layout.addWidget(self.show_webhook_checkbox)
        self.test_button = QPushButton("Проверить соединение")
        self.test_button.clicked.connect(self._test_connection)
        _configure_settings_action_button(self.test_button)
        general_layout.addWidget(self.test_button)

        self.webhook_status = QLabel("")
        _configure_settings_status_label(self.webhook_status)
        general_layout.addWidget(self.webhook_status)

        portal_hint = QLabel(
            "Параметры реестра проектов на портале. Можно определить автоматически "
            "после проверки соединения."
        )
        portal_hint.setWordWrap(True)
        general_layout.addWidget(portal_hint)
        _fit_settings_hint_label(portal_hint)

        portal_form = QFormLayout()
        _configure_settings_form_layout(portal_form)
        self.registry_title_edit = QLineEdit()
        self.registry_title_edit.setText(portal.projects_registry_title)
        _configure_settings_form_field(self.registry_title_edit)
        portal_form.addRow("Название СПА проектов", self.registry_title_edit)

        self.entity_type_spin = QSpinBox()
        self.entity_type_spin.setRange(1, 9999)
        self.entity_type_spin.setValue(portal.projects_entity_type_id)
        _configure_settings_form_field(self.entity_type_spin)
        portal_form.addRow("entityTypeId СПА", self.entity_type_spin)

        self.executor_fields_edit = QLineEdit()
        self.executor_fields_edit.setPlaceholderText("ufCrm16MainIspolnitel, ufCrm16Supporters")
        self.executor_fields_edit.setText(", ".join(portal.projects_executor_fields))
        _configure_settings_form_field(self.executor_fields_edit)
        portal_form.addRow("Поля фильтра (через запятую)", self.executor_fields_edit)
        general_layout.addLayout(portal_form)

        self.discover_button = QPushButton("Определить с портала")
        self.discover_button.clicked.connect(self._discover_portal)
        _configure_settings_action_button(self.discover_button)
        general_layout.addWidget(self.discover_button)

        self.portal_status = QLabel("")
        _configure_settings_status_label(self.portal_status)
        general_layout.addWidget(self.portal_status)
        general_layout.addStretch(1)
        tabs.addTab(_wrap_settings_tab(general_tab), "Битрикс24")

        webdav_tab = QWidget()
        webdav_layout = QVBoxLayout(webdav_tab)
        webdav_layout.setContentsMargins(0, 12, 0, 0)
        webdav_layout.setSpacing(12)

        webdav_hint = QLabel(
            "Синхронизация data.json по WebDAV (Nextcloud, Яндекс.Диск WebDAV и др.). "
            "Пароль хранится локально в ~/.config/tasktimer/webdav.json и не попадает в облако."
        )
        webdav_hint.setWordWrap(True)
        webdav_layout.addWidget(webdav_hint)
        _fit_settings_hint_label(webdav_hint)

        self.webdav_enabled_checkbox = QCheckBox("Включить синхронизацию WebDAV")
        self.webdav_enabled_checkbox.setChecked(webdav.enabled)
        webdav_layout.addWidget(self.webdav_enabled_checkbox)

        webdav_form = QFormLayout()
        _configure_settings_form_layout(webdav_form)
        self.webdav_url_edit = QLineEdit()
        self.webdav_url_edit.setPlaceholderText("https://cloud.example.com/remote.php/dav/files/user/")
        self.webdav_url_edit.setText(webdav.url)
        _configure_settings_form_field(self.webdav_url_edit)
        webdav_form.addRow("URL WebDAV", self.webdav_url_edit)

        self.webdav_username_edit = QLineEdit()
        self.webdav_username_edit.setText(webdav.username)
        _configure_settings_form_field(self.webdav_username_edit)
        webdav_form.addRow("Имя пользователя", self.webdav_username_edit)

        self.webdav_password_edit = QLineEdit()
        self.webdav_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.webdav_password_edit.setText(webdav.password)
        _configure_settings_form_field(self.webdav_password_edit)
        webdav_form.addRow("Пароль", self.webdav_password_edit)

        self.webdav_remote_path_edit = QLineEdit()
        self.webdav_remote_path_edit.setPlaceholderText("tasktimer/data.json")
        self.webdav_remote_path_edit.setText(webdav.remote_path)
        _configure_settings_form_field(self.webdav_remote_path_edit)
        webdav_form.addRow("Путь к файлу на сервере", self.webdav_remote_path_edit)
        webdav_layout.addLayout(webdav_form)

        self.webdav_sync_startup_checkbox = QCheckBox("Скачивать и объединять при запуске")
        self.webdav_sync_startup_checkbox.setChecked(webdav.sync_on_startup)
        webdav_layout.addWidget(self.webdav_sync_startup_checkbox)

        self.webdav_sync_shutdown_checkbox = QCheckBox("Загружать на сервер при выходе")
        self.webdav_sync_shutdown_checkbox.setChecked(webdav.sync_on_shutdown)
        webdav_layout.addWidget(self.webdav_sync_shutdown_checkbox)

        self.webdav_shutdown_upload_only_checkbox = QCheckBox(
            "При выходе только отправить локальную копию (без слияния с облаком)"
        )
        self.webdav_shutdown_upload_only_checkbox.setChecked(webdav.shutdown_upload_only)
        _configure_settings_checkbox(self.webdav_shutdown_upload_only_checkbox)
        webdav_layout.addWidget(self.webdav_shutdown_upload_only_checkbox)

        upload_only_hint = QLabel(
            "Если выключено — перед отправкой при выходе данные объединяются с сервером. "
            "При конфликте при следующем запуске будет уведомление."
        )
        upload_only_hint.setWordWrap(True)
        webdav_layout.addWidget(upload_only_hint)
        _fit_settings_hint_label(upload_only_hint)

        self.webdav_sync_interval_spin = QSpinBox()
        self.webdav_sync_interval_spin.setRange(0, 1440)
        self.webdav_sync_interval_spin.setSuffix(" мин")
        self.webdav_sync_interval_spin.setValue(webdav.sync_interval_minutes)
        self.webdav_sync_interval_spin.setToolTip(
            "0 — периодическая проверка выключена. Иначе каждые N минут проверяется сервер; "
            "при изменениях с другого устройства появится запрос «Скачать и объединить». "
            "Работает в фоне, в том числе когда окно свёрнуто в трей. "
            "На Android в фоне минимум 15 минут (ограничение ОС); в открытом приложении — точный интервал."
        )
        _configure_settings_form_field(self.webdav_sync_interval_spin)
        webdav_form.addRow("Синхронизировать каждые", self.webdav_sync_interval_spin)

        self.webdav_remind_later_combo = QComboBox()
        for minutes in REMIND_LATER_MINUTES_CHOICES:
            self.webdav_remind_later_combo.addItem(f"{minutes} мин", minutes)
        remind_index = REMIND_LATER_MINUTES_CHOICES.index(webdav.sync_remind_later_minutes) if webdav.sync_remind_later_minutes in REMIND_LATER_MINUTES_CHOICES else 2
        self.webdav_remind_later_combo.setCurrentIndex(remind_index)
        self.webdav_remind_later_combo.setToolTip(
            "После «Позже» запрос повторится через выбранный интервал для той же версии на сервере. "
            "При появлении новой версии таймер сбрасывается."
        )
        _configure_settings_form_field(self.webdav_remind_later_combo)
        webdav_form.addRow("Напомнить через (кнопка «Позже»)", self.webdav_remind_later_combo)

        self.webdav_test_button = QPushButton("Проверить WebDAV")
        self.webdav_test_button.clicked.connect(self._test_webdav)
        _configure_settings_action_button(self.webdav_test_button)
        webdav_layout.addWidget(self.webdav_test_button)
        self.webdav_pull_button = QPushButton("Скачать и объединить")
        self.webdav_pull_button.clicked.connect(self._webdav_pull_now)
        _configure_settings_action_button(self.webdav_pull_button)
        webdav_layout.addWidget(self.webdav_pull_button)
        self.webdav_push_button = QPushButton("Загрузить сейчас")
        self.webdav_push_button.clicked.connect(self._webdav_push_now)
        _configure_settings_action_button(self.webdav_push_button)
        webdav_layout.addWidget(self.webdav_push_button)

        self.webdav_status = QLabel(self._webdav_status_text(webdav))
        _configure_settings_status_label(self.webdav_status)
        webdav_layout.addWidget(self.webdav_status)
        _fit_settings_hint_label(self.webdav_status)
        webdav_layout.addStretch(1)
        tabs.addTab(_wrap_settings_tab(webdav_tab), "WebDAV")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._settings_tabs = tabs
        self._settings_buttons = buttons
        self._settings_layout_sync_width = -1
        tabs.currentChanged.connect(lambda _index: self._sync_settings_tabs_layout())
        self.setMinimumWidth(SETTINGS_DIALOG_MIN_WIDTH)
        self._apply_settings_dialog_height()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._settings_layout_sync_width = -1
        self._sync_settings_tabs_layout()
        self._settings_layout_sync_width = self.width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width_changed = event.size().width() != self._settings_layout_sync_width
        if width_changed:
            self._settings_layout_sync_width = event.size().width()
        if width_changed or self.height() < self.minimumHeight():
            self._sync_settings_tabs_layout()

    def _settings_status_label_width(self) -> int:
        current = self._settings_tabs.currentWidget()
        if isinstance(current, QScrollArea):
            return _settings_tab_content_width(current, dialog_width=self.width())
        return _settings_dialog_content_width(self.width())

    def _settings_dialog_chrome_height(self) -> int:
        if self.isVisible() and self.height() > 0:
            current = self._settings_tabs.currentWidget()
            if isinstance(current, QScrollArea) and current.height() > 0:
                measured = self.height() - current.height()
                if measured > 0:
                    return measured

        root_layout = self.layout()
        if root_layout is None:
            return SETTINGS_DIALOG_CHROME_HEIGHT
        margins = root_layout.contentsMargins().top() + root_layout.contentsMargins().bottom()
        tab_bar_height = self._settings_tabs.tabBar().sizeHint().height()
        buttons_height = self._settings_buttons.sizeHint().height()
        spacing = root_layout.spacing() * max(0, root_layout.count() - 1)
        estimated = margins + tab_bar_height + buttons_height + spacing
        return max(estimated, SETTINGS_DIALOG_CHROME_HEIGHT)

    def _cap_settings_dialog_height(self, ideal_height: int) -> int:
        capped = max(SETTINGS_DIALOG_MIN_HEIGHT, ideal_height)
        screen = self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return capped
        available_height = screen.availableGeometry().height()
        screen_cap = min(
            int(available_height * SETTINGS_DIALOG_SCREEN_HEIGHT_RATIO),
            available_height,
        )
        if capped <= screen_cap:
            return capped
        return max(screen_cap, min(available_height, SETTINGS_DIALOG_MIN_HEIGHT))

    def _measure_all_settings_tab_heights(self) -> list[int]:
        content_heights: list[int] = []
        for index in range(self._settings_tabs.count()):
            scroll = self._settings_tabs.widget(index)
            if not isinstance(scroll, QScrollArea):
                continue
            content_width = _settings_tab_content_width(
                scroll,
                dialog_width=self.width(),
            )
            content_heights.append(
                _measure_settings_tab_content_height(scroll, content_width)
            )
        return content_heights

    def _effective_settings_dialog_height(self, max_content_height: int) -> int:
        ideal_height = max_content_height + self._settings_dialog_chrome_height()
        return self._cap_settings_dialog_height(ideal_height)

    def _sync_settings_tabs_layout(self) -> None:
        content_heights = self._measure_all_settings_tab_heights()
        max_content = max(content_heights) if content_heights else 0
        min_height = self._effective_settings_dialog_height(max_content)
        if self.minimumHeight() != min_height:
            self.setMinimumHeight(min_height)
        if self.isVisible() and self.height() < min_height:
            self.resize(self.width(), min_height)

    def _apply_settings_dialog_height(self) -> None:
        self._sync_settings_tabs_layout()
        self.resize(
            max(self.width(), SETTINGS_DIALOG_DEFAULT_WIDTH),
            max(self.height(), SETTINGS_DIALOG_DEFAULT_HEIGHT, self.minimumHeight()),
        )

    def _toggle_webhook_echo(self, shown: bool) -> None:
        self.webhook_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )

    def _test_connection(self) -> None:
        url = self.webhook_edit.text().strip()
        if not looks_like_webhook(url):
            self._set_status("✗ Похоже на неверный формат URL (ожидается …/rest/…)", ok=False)
            return
        self.test_button.setEnabled(False)
        self._set_status("Проверяю…", ok=None)

        self._test_thread = _CallableThread(
            lambda: bitrix_client(self.controller, url).test_connection(), self
        )
        self._test_thread.succeeded.connect(self._on_test_ok)
        self._test_thread.failed.connect(self._on_test_failed)
        self._test_thread.finished.connect(lambda: self.test_button.setEnabled(True))
        self._test_thread.start()

    def _on_test_ok(self, profile: object) -> None:
        name = ""
        if isinstance(profile, dict):
            name = " ".join(
                str(profile.get(key, "")).strip() for key in ("NAME", "LAST_NAME")
            ).strip()
        suffix = f": {name}" if name else ""
        self._set_status(f"✓ Подключение успешно{suffix}", ok=True)

    def _on_test_failed(self, message: str) -> None:
        self._set_status(f"✗ Не удалось подключиться: {message}", ok=False)

    def _discover_portal(self) -> None:
        url = self.webhook_edit.text().strip()
        if not looks_like_webhook(url):
            self._set_portal_status("✗ Сначала укажите корректный URL вебхука", ok=False)
            return
        self.discover_button.setEnabled(False)
        self._set_portal_status("Определяю параметры портала…", ok=None)

        def work():
            client = bitrix_client(self.controller, url)
            return client.discover_portal_config()

        self._discover_thread = _CallableThread(work, self)
        self._discover_thread.succeeded.connect(self._on_discover_ok)
        self._discover_thread.failed.connect(self._on_discover_failed)
        self._discover_thread.finished.connect(lambda: self.discover_button.setEnabled(True))
        self._discover_thread.start()

    def _on_discover_ok(self, config: object) -> None:
        if not isinstance(config, BitrixPortalConfig):
            self._set_portal_status("✗ Неожиданный ответ портала", ok=False)
            return
        self.registry_title_edit.setText(config.projects_registry_title)
        self.entity_type_spin.setValue(config.projects_entity_type_id)
        self.executor_fields_edit.setText(", ".join(config.projects_executor_fields))
        self._set_portal_status(
            f"✓ СПА «{config.projects_registry_title}» (id {config.projects_entity_type_id})",
            ok=True,
        )

    def _on_discover_failed(self, message: str) -> None:
        self._set_portal_status(f"✗ {message}", ok=False)

    def portal_config(self) -> BitrixPortalConfig:
        fields = tuple(
            part.strip()
            for part in self.executor_fields_edit.text().split(",")
            if part.strip()
        )
        return BitrixPortalConfig(
            projects_entity_type_id=self.entity_type_spin.value(),
            projects_executor_fields=fields or BitrixPortalConfig().projects_executor_fields,
            projects_registry_title=self.registry_title_edit.text().strip()
            or BitrixPortalConfig().projects_registry_title,
        )

    def webdav_config(self) -> WebDavConfig:
        current = load_webdav_config()
        return WebDavConfig(
            enabled=self.webdav_enabled_checkbox.isChecked(),
            url=self.webdav_url_edit.text().strip(),
            username=self.webdav_username_edit.text().strip(),
            password=self.webdav_password_edit.text(),
            remote_path=self.webdav_remote_path_edit.text().strip() or current.remote_path,
            sync_on_startup=self.webdav_sync_startup_checkbox.isChecked(),
            sync_on_shutdown=self.webdav_sync_shutdown_checkbox.isChecked(),
            shutdown_upload_only=self.webdav_shutdown_upload_only_checkbox.isChecked(),
            sync_interval_minutes=self.webdav_sync_interval_spin.value(),
            sync_remind_later_minutes=int(self.webdav_remind_later_combo.currentData()),
            last_sync_at=current.last_sync_at,
            last_error=current.last_error,
            device_id=current.device_id,
            last_remote_content_hash=current.last_remote_content_hash,
            last_sync_had_conflict=current.last_sync_had_conflict,
            pending_notice=current.pending_notice,
            pending_remote_hash=current.pending_remote_hash,
            pending_remote_remind_at=current.pending_remote_remind_at,
        )

    @staticmethod
    def _webdav_status_text(config: WebDavConfig) -> str:
        if config.last_sync_at:
            base = f"Последняя синхронизация: {config.last_sync_at}"
        else:
            base = "Синхронизация ещё не выполнялась"
        if config.last_error:
            return f"{base}\nПоследняя ошибка: {config.last_error}"
        return base

    def _set_webdav_status(self, text: str, ok: bool | None) -> None:
        color = {True: "#2d6b40", False: "#9b3c3c", None: "#5f6b7c"}[ok]
        self.webdav_status.setText(text)
        self.webdav_status.setStyleSheet(f"color: {color}; background: transparent;")
        _fit_settings_hint_label(self.webdav_status, self._settings_status_label_width())
        self._sync_settings_tabs_layout()

    def _test_webdav(self) -> None:
        config = self.webdav_config()
        if not config.is_configured():
            self._set_webdav_status("✗ Укажите URL и имя пользователя", ok=False)
            return
        self.webdav_test_button.setEnabled(False)
        self._set_webdav_status("Проверяю WebDAV…", ok=None)
        self._webdav_test_thread = _CallableThread(lambda: test_webdav_connection(config), self)
        self._webdav_test_thread.succeeded.connect(
            lambda message: self._set_webdav_status(f"✓ {message}", ok=True)
        )
        self._webdav_test_thread.failed.connect(
            lambda message: self._set_webdav_status(f"✗ {message}", ok=False)
        )
        self._webdav_test_thread.finished.connect(lambda: self.webdav_test_button.setEnabled(True))
        self._webdav_test_thread.start()

    def _webdav_pull_now(self) -> None:
        config = self.webdav_config()
        if not config.is_configured():
            self._set_webdav_status("✗ Укажите URL и имя пользователя", ok=False)
            return
        self._set_webdav_buttons_enabled(False)
        self._set_webdav_status("Скачиваю и объединяю…", ok=None)

        def work() -> SyncOutcome:
            return pull_and_merge(self.controller.storage, config, require_enabled=False)

        self._webdav_sync_thread = _CallableThread(work, self)
        self._webdav_sync_thread.succeeded.connect(self._on_webdav_pull_ok)
        self._webdav_sync_thread.failed.connect(
            lambda message: self._set_webdav_status(f"✗ {message}", ok=False)
        )
        self._webdav_sync_thread.finished.connect(self._on_webdav_sync_finished)
        self._webdav_sync_thread.start()

    def _webdav_push_now(self) -> None:
        config = self.webdav_config()
        if not config.is_configured():
            self._set_webdav_status("✗ Укажите URL и имя пользователя", ok=False)
            return
        self.controller.save()
        self._set_webdav_buttons_enabled(False)
        self._set_webdav_status("Загружаю на сервер…", ok=None)

        def work() -> SyncOutcome:
            return push_local(self.controller.storage, config, require_enabled=False)

        self._webdav_sync_thread = _CallableThread(work, self)
        self._webdav_sync_thread.succeeded.connect(self._on_webdav_push_ok)
        self._webdav_sync_thread.failed.connect(
            lambda message: self._set_webdav_status(f"✗ {message}", ok=False)
        )
        self._webdav_sync_thread.finished.connect(self._on_webdav_sync_finished)
        self._webdav_sync_thread.start()

    def _on_webdav_pull_ok(self, outcome: object) -> None:
        self.controller.reload_state_from_storage()
        sync_outcome = outcome if isinstance(outcome, SyncOutcome) else SyncOutcome()
        task_count = len(sync_outcome.state.tasks) if sync_outcome.state else len(self.controller.state.tasks)
        message = f"✓ Объединено, задач в базе: {task_count}"
        if sync_outcome.notice:
            message = f"{message}. {sync_outcome.notice}"
        self._set_webdav_status(message, ok=True)
        parent = self.parent()
        if isinstance(parent, MainWindow):
            parent.refresh_ui()

    def _on_webdav_push_ok(self, outcome: object) -> None:
        self.controller.reload_state_from_storage()
        sync_outcome = outcome if isinstance(outcome, SyncOutcome) else SyncOutcome()
        if sync_outcome.notice:
            self._set_webdav_status(f"✓ {sync_outcome.notice}", ok=True)
        else:
            self._set_webdav_status("✓ База загружена на WebDAV", ok=True)

    def _on_webdav_sync_finished(self) -> None:
        self._set_webdav_buttons_enabled(True)
        config = load_webdav_config()
        status_ok: bool | None = False if config.last_error else None
        self._set_webdav_status(self._webdav_status_text(config), ok=status_ok)

    def _set_webdav_buttons_enabled(self, enabled: bool) -> None:
        self.webdav_test_button.setEnabled(enabled)
        self.webdav_pull_button.setEnabled(enabled)
        self.webdav_push_button.setEnabled(enabled)

    def _set_status(self, text: str, ok: bool | None) -> None:
        color = {True: "#2d6b40", False: "#9b3c3c", None: "#5f6b7c"}[ok]
        self.webhook_status.setText(text)
        self.webhook_status.setStyleSheet(f"color: {color}; background: transparent;")
        _fit_settings_hint_label(self.webhook_status, self._settings_status_label_width())
        self._sync_settings_tabs_layout()

    def _set_portal_status(self, text: str, ok: bool | None) -> None:
        color = {True: "#2d6b40", False: "#9b3c3c", None: "#5f6b7c"}[ok]
        self.portal_status.setText(text)
        self.portal_status.setStyleSheet(f"color: {color}; background: transparent;")
        _fit_settings_hint_label(self.portal_status, self._settings_status_label_width())
        self._sync_settings_tabs_layout()

    def _await_worker_threads(self) -> None:
        for thread in (
            self._test_thread,
            self._discover_thread,
            self._webdav_test_thread,
            self._webdav_sync_thread,
        ):
            if thread is not None and thread.isRunning():
                thread.wait(5000)

    def accept(self) -> None:
        self._await_worker_threads()
        super().accept()

    def reject(self) -> None:
        self._await_worker_threads()
        super().reject()


class TaskEditDialog(QDialog):
    def __init__(self, controller: AppController, task: Task, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.task_id = task.id
        self.setWindowTitle("Редактировать задачу")
        self.resize(480, 280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        heading = QLabel("Редактировать задачу")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.title_edit = QLineEdit(task.title)
        self.title_edit.setPlaceholderText("Название задачи")
        form.addRow("Название", self.title_edit)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Описание (необязательно)")
        self.description_edit.setPlainText(task.description)
        self.description_edit.document().contentsChanged.connect(
            lambda: fit_plain_text_edit_height(self.description_edit)
        )
        form.addRow("Описание", self.description_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        fit_plain_text_edit_height(self.description_edit)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        fit_plain_text_edit_height(self.description_edit)

    def accept(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи.")
            return
        try:
            self.controller.update_task(
                self.task_id,
                title=title,
                description=self.description_edit.toPlainText(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        super().accept()


class SessionEditDialog(QDialog):
    def __init__(self, controller: AppController, task: Task, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.task = task
        self.selected_session_id: str | None = None
        self._transfer_thread: _CallableThread | None = None
        self.setWindowTitle("История сессий")
        self.resize(700, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel("История сессий")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        subtitle = QLabel(task.title)
        subtitle.setObjectName("descriptionLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(4)

        self.select_all_checkbox = QCheckBox("Выделить всё")
        self.select_all_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all_checkbox.toggled.connect(self._toggle_select_all)
        layout.addWidget(self.select_all_checkbox)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["", "Начало", "Окончание", "Длительность", "Комментарий", "Передано"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.horizontalHeader().setHighlightSections(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._load_current_session)
        layout.addWidget(self.table, 1)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setContentsMargins(0, 6, 0, 0)
        self.start_edit = QDateTimeEdit()
        self.start_edit.setObjectName("historyStart")
        self.start_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setFixedHeight(34)
        _style_calendar_field(self.start_edit)
        form.addRow("Начало", self.start_edit)

        self.end_edit = QDateTimeEdit()
        self.end_edit.setObjectName("historyEnd")
        self.end_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setFixedHeight(34)
        _style_calendar_field(self.end_edit)
        form.addRow("Окончание", self.end_edit)

        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setObjectName("historyComment")
        self.comment_edit.setPlaceholderText("Комментарий к интервалу (необязательно)")
        self.comment_edit.setFixedHeight(56)
        form.addRow("Комментарий", self.comment_edit)
        layout.addLayout(form)
        layout.addSpacing(4)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        add_button = QPushButton("Добавить запись")
        add_button.setObjectName("ghostButton")
        add_button.setFixedHeight(34)
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self._add_session)
        actions.addWidget(add_button)
        self.delete_session_button = QPushButton("Удалить запись")
        self.delete_session_button.setObjectName("deleteGhostButton")
        self.delete_session_button.setFixedHeight(34)
        self.delete_session_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_session_button.clicked.connect(self._delete_current_session)
        actions.addWidget(self.delete_session_button)
        self.transfer_button = QPushButton("Передать в Битрикс")
        self.transfer_button.setObjectName("ghostButton")
        self.transfer_button.setFixedHeight(34)
        self.transfer_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.transfer_button.clicked.connect(self._transfer_to_bitrix)
        link = self.task.bitrix
        self.transfer_button.setEnabled(
            isinstance(link, dict) and link.get("source") in ("project", "task") and bool(link.get("id"))
        )
        actions.addWidget(self.transfer_button)
        actions.addStretch()
        save_button = QPushButton("Сохранить интервал")
        save_button.setObjectName("primaryButton")
        save_button.setFixedHeight(34)
        save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        save_button.clicked.connect(self._save_current_session)
        actions.addWidget(save_button)
        layout.addLayout(actions)

        self._reload()

    def _await_worker_threads(self) -> None:
        thread = self._transfer_thread
        if thread is not None and thread.isRunning():
            thread.wait(8000)

    def reject(self) -> None:
        self._await_worker_threads()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._await_worker_threads()
        super().closeEvent(event)

    @staticmethod
    def _readonly_cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        return item

    def _toggle_select_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(state)
        self.table.blockSignals(False)

    def _reload(self) -> None:
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setChecked(False)
        self.select_all_checkbox.blockSignals(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for session in self.task.sessions:
            start = datetime.fromisoformat(session.started_at)
            end = datetime.fromisoformat(session.ended_at) if session.ended_at else None
            duration = session.duration_seconds(datetime.now())
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, session.id)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, self._readonly_cell(start.strftime("%d.%m.%Y %H:%M:%S")))
            self.table.setItem(
                row, 2,
                self._readonly_cell(end.strftime("%d.%m.%Y %H:%M:%S") if end else "идёт"),
            )
            self.table.setItem(row, 3, self._readonly_cell(format_duration(duration)))
            self.table.setItem(row, 4, self._readonly_cell(session.comment))
            self.table.setItem(row, 5, self._readonly_cell(session.bitrix_record_id or ""))
        self.table.blockSignals(False)
        if self.table.rowCount():
            self.table.selectRow(0)
        else:
            self.selected_session_id = None
            end_q = QDateTime.currentDateTime()
            self.end_edit.setDateTime(end_q)
            self.start_edit.setDateTime(end_q.addSecs(-3600))
        self.delete_session_button.setEnabled(self.table.rowCount() > 0)

    def _session_id_at(self, row: int) -> str | None:
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _current_session_id(self) -> str | None:
        row = self.table.currentRow()
        return self._session_id_at(row) if row >= 0 else None

    def _add_session(self) -> None:
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        try:
            session = self.controller.add_session(
                self.task.id,
                start,
                end,
                comment=self.comment_edit.toPlainText(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        self.task = self.controller.find_task(self.task.id)
        self._reload()
        for row in range(self.table.rowCount()):
            if self._session_id_at(row) == session.id:
                self.table.selectRow(row)
                break

    def _delete_current_session(self) -> None:
        ids = [
            self._session_id_at(row)
            for row in range(self.table.rowCount())
            if self.table.item(row, 0)
            and self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        if not ids:
            current = self._current_session_id()
            ids = [current] if current else []
        ids = [sid for sid in ids if sid]
        if not ids:
            return
        answer = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить выбранные записи ({len(ids)})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for sid in ids:
            try:
                self.controller.delete_session(self.task.id, sid)
            except KeyError:
                pass
        self.task = self.controller.find_task(self.task.id)
        self._reload()

    def _load_current_session(self) -> None:
        session_id = self._current_session_id()
        if session_id is None:
            return
        session = next((entry for entry in self.task.sessions if entry.id == session_id), None)
        if session is None:
            return
        self.selected_session_id = session.id
        self.start_edit.setDateTime(QDateTime.fromString(session.started_at, Qt.DateFormat.ISODate))
        end_value = session.ended_at or datetime.now().isoformat()
        self.end_edit.setDateTime(QDateTime.fromString(end_value, Qt.DateFormat.ISODate))
        self.comment_edit.setPlainText(session.comment)

    def _save_current_session(self) -> None:
        if not self.selected_session_id:
            return
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        try:
            self.controller.update_session(
                self.task.id,
                self.selected_session_id,
                start,
                end,
                comment=self.comment_edit.toPlainText(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        self.task = self.controller.find_task(self.task.id)
        self._reload()
        QMessageBox.information(self, "Сохранено", "Интервал обновлен.")

    def _transfer_to_bitrix(self) -> None:
        link = self.task.bitrix
        if not (isinstance(link, dict) and link.get("source") in ("project", "task") and link.get("id")):
            QMessageBox.information(self, "Битрикс24", "Задача не связана с Битрикс24.")
            return
        sessions = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                session = next(
                    (s for s in self.task.sessions if s.id == self._session_id_at(row)), None
                )
                if session and not session.bitrix_record_id:
                    sessions.append(session)
        if not sessions:
            QMessageBox.information(self, "Битрикс24", "Отметьте непереданные интервалы галочками.")
            return
        webhook = self.controller.bitrix_webhook()
        if not looks_like_webhook(webhook):
            QMessageBox.warning(self, "Битрикс24", "Укажите URL вебхука в настройках.")
            return
        name, ok = QInputDialog.getText(
            self,
            "Передача времени",
            "Название записи:",
            text=next((s.comment for s in sessions if s.comment.strip()), "") or self.task.title,
        )
        name = (name or "").strip()
        if not ok or not name:
            return
        total_seconds = sum(s.duration_seconds(datetime.now()) for s in sessions)
        session_ids = [s.id for s in sessions]
        source = link["source"]
        entity_id = link["id"]
        last_date = max(s.start_dt for s in sessions).date().isoformat()
        task_id = self.task.id
        storage = self.controller.storage
        self.transfer_button.setEnabled(False)

        def work():
            client = bitrix_client(self.controller, webhook)
            if source == "project":
                hours = seconds_to_worklog_hours(total_seconds)
                record_id = client.add_project_time(
                    entity_id, last_date, hours, name, client.current_user_id()
                )
            else:
                record_id = client.add_task_time(entity_id, total_seconds, name)
            record_transfer_result(storage, task_id, session_ids, record_id)
            return record_id

        self._transfer_thread = _CallableThread(work, self)
        self._transfer_thread.succeeded.connect(
            lambda record_id: self._on_transferred(session_ids, record_id)
        )
        self._transfer_thread.failed.connect(self._on_transfer_failed)
        self._transfer_thread.start()

    def _on_transferred(self, session_ids, record_id) -> None:
        self.controller.mark_sessions_transferred(self.task.id, session_ids, record_id)
        self.controller.finalize_sessions_transfer(self.task.id, session_ids, record_id)
        self.task = self.controller.find_task(self.task.id)
        self.transfer_button.setEnabled(True)
        self._reload()

    def _on_transfer_failed(self, message: str) -> None:
        self.transfer_button.setEnabled(True)
        QMessageBox.warning(self, "Битрикс24", f"Не удалось передать время: {message}")


class PortalImportDialog(QDialog):
    """Pick projects (СПА 150) or tasks from the portal and import them."""

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Импорт с портала Битрикс24")
        self.resize(640, 540)
        self._load_thread: _CallableThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Loader shown while the portal lists are fetched.
        self.loader = QWidget()
        loader_layout = QVBoxLayout(self.loader)
        loader_layout.addStretch(1)
        self.loading_label = QLabel("Загрузка с портала…")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loader_layout.addWidget(self.loading_label)
        progress_row = QHBoxLayout()
        progress_row.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate (busy) indicator
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(240)
        progress_row.addWidget(self.progress)
        progress_row.addStretch(1)
        loader_layout.addLayout(progress_row)
        loader_layout.addStretch(1)
        layout.addWidget(self.loader, 1)

        self.tabs = QTabWidget()
        self.project_list, project_tab = self._build_list_tab("Поиск проекта…")
        self.task_list, task_tab = self._build_list_tab("Поиск задачи…")
        self.tabs.addTab(project_tab, "Проекты")
        self.tabs.addTab(task_tab, "Задачи")
        self.tabs.hide()
        layout.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        self.import_button = QPushButton("Импортировать выбранное")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._do_import)
        buttons.addWidget(self.import_button)
        layout.addLayout(buttons)

        self._start_load()

    def _build_list_tab(self, placeholder: str):
        tab = QWidget()
        column = QVBoxLayout(tab)
        column.setContentsMargins(0, 8, 0, 0)
        column.setSpacing(8)
        search = QLineEdit()
        search.setPlaceholderText(placeholder)
        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        search.textChanged.connect(lambda text, lw=list_widget: self._filter_list(lw, text))
        column.addWidget(search)
        column.addWidget(list_widget, 1)
        return list_widget, tab

    def _filter_list(self, list_widget: QListWidget, text: str) -> None:
        needle = text.strip().lower()
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            item.setHidden(needle not in item.text().lower())

    def _show_loader(self, text: str, busy: bool = True) -> None:
        self.loading_label.setText(text)
        self.loading_label.setStyleSheet(
            f"color: {'#5f6b7c' if busy else '#9b3c3c'}; background: transparent;"
        )
        self.progress.setVisible(busy)
        self.tabs.hide()
        self.loader.show()

    def _show_content(self) -> None:
        self.loader.hide()
        self.tabs.show()

    def _start_load(self) -> None:
        webhook = self.controller.bitrix_webhook()
        if not looks_like_webhook(webhook):
            self._show_loader("Сначала укажите URL вебхука в Настройках.", busy=False)
            return
        self._show_loader("Загрузка с портала…", busy=True)

        def work():
            client = bitrix_client(self.controller, webhook)
            user_id = client.current_user_id()
            return {
                "projects": client.list_projects(user_id),
                "tasks": client.list_tasks(user_id),
            }

        self._load_thread = _CallableThread(work, self)
        self._load_thread.succeeded.connect(self._on_loaded)
        self._load_thread.failed.connect(self._on_failed)
        self._load_thread.start()

    def _on_failed(self, message: str) -> None:
        self._show_loader(f"Не удалось загрузить: {message}", busy=False)

    def _on_loaded(self, data: object) -> None:
        data = data if isinstance(data, dict) else {}
        projects = data.get("projects", [])
        tasks = data.get("tasks", [])
        self._fill(self.project_list, projects, "project")
        self._fill(self.task_list, tasks, "task")
        self._set_status(
            f"Проектов: {len(projects)} · Задач: {len(tasks)}. "
            "Выбери нужные (можно несколько) и нажми «Импортировать выбранное».",
            ok=True,
        )
        self.import_button.setEnabled(True)
        self._show_content()

    def _fill(self, list_widget: QListWidget, items: list, source: str) -> None:
        list_widget.clear()
        for entry in items:
            title = entry.get("title") or f"#{entry.get('id')}"
            item = QListWidgetItem(title)
            item.setData(
                Qt.ItemDataRole.UserRole,
                {"source": source, "id": str(entry.get("id")), "title": entry.get("title", "")},
            )
            list_widget.addItem(item)

    def _do_import(self) -> None:
        chosen = [
            item.data(Qt.ItemDataRole.UserRole)
            for list_widget in (self.project_list, self.task_list)
            for item in list_widget.selectedItems()
        ]
        if not chosen:
            self._set_status("Ничего не выбрано.", ok=False)
            return
        self.imported_count, _ = self.controller.import_bitrix_items(chosen)
        self.accept()

    def _set_status(self, text: str, ok: bool | None) -> None:
        color = {True: "#2d6b40", False: "#9b3c3c", None: "#5f6b7c"}[ok]
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; background: transparent;")

    def _await_thread(self) -> None:
        thread = self._load_thread
        if thread is not None and thread.isRunning():
            thread.wait(8000)

    def accept(self) -> None:
        self._await_thread()
        super().accept()

    def reject(self) -> None:
        self._await_thread()
        super().reject()


class MainWindow(QMainWindow):
    focus_presets = (5, 10, 20, 30, 40)

    def __init__(self, controller: AppController, app: QApplication) -> None:
        super().__init__()
        self.controller = controller
        self.app = app
        self._current_view = "plan"
        self._selected_date: str | None = None
        self._portal_sync_queue: list = []
        self._portal_sync_busy = False
        self._task_rows: dict[str, TaskRow] = {}
        self._task_rows_reference_date: str | None = None
        self._pinned_task_row_id: str | None = None
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.app_icon = build_tray_app_icon(self.style())
        self.setWindowIcon(self.app_icon)
        self.setWindowTitle(resolve_app_title())
        self.resize(980, 680)
        self.create_dialog = CreateTaskDialog(self.controller, self)
        self.create_dialog.create_requested.connect(self._create_task)
        self._mini_task_id: str | None = None
        self._tray_collapsed = False
        self._floating_user_dismissed = False
        self._last_tray_activation_at = 0.0
        self.floating = FloatingTimer()
        self.floating.stop_requested.connect(self._floating_stop)
        self.floating.start_requested.connect(self._floating_start)
        self.floating.restore_requested.connect(self._restore_from_tray)
        self.floating.close_requested.connect(self._floating_close)
        self._load_fonts()
        self._build_ui()
        self._build_menu_bar()
        self._build_tray()
        install_tray_icon_theme_refresh(self._refresh_app_icon)
        self._apply_styles()
        self._apply_window_constraints()
        self.refresh_ui()

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start()
        self._webdav_periodic_timer = QTimer(self)
        self._webdav_periodic_timer.timeout.connect(self._webdav_periodic_sync)
        self._webdav_main_sync_thread: _CallableThread | None = None
        self._webdav_check_thread: _CallableThread | None = None
        self._webdav_remote_prompt_open = False
        self._configure_webdav_periodic_timer()
        QTimer.singleShot(0, self._run_deferred_startup_sync)

    def _run_deferred_startup_sync(self) -> None:
        if self.controller.run_deferred_startup_sync():
            self.refresh_ui()
            QTimer.singleShot(0, self._offer_focus_resume_if_pending)
        QTimer.singleShot(300, self._show_startup_notices)
        QTimer.singleShot(350, self._offer_focus_resume_if_pending)

    def _offer_focus_resume_if_pending(self) -> None:
        if not self.controller.focus_resume_offer_pending:
            return
        paused_id = self.controller.focus_paused_task_id
        if not paused_id:
            self.controller.focus_resume_offer_pending = False
            return
        self.controller.focus_resume_offer_pending = False
        self._prompt_focus_resume(paused_id)

    def _prompt_focus_resume(self, paused_task_id: str) -> None:
        try:
            task = self.controller.find_task(paused_task_id)
        except KeyError:
            self.controller.take_focus_paused_task_id()
            return
        if task.is_completed():
            self.controller.take_focus_paused_task_id()
            return
        answer = QMessageBox.question(
            self,
            "Фокус-сессия завершена",
            f"Время концентрации вышло.\n\nПродолжить задачу «{task.title}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        self.controller.take_focus_paused_task_id()
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.start_task(paused_task_id)
        self.refresh_ui()

    def _show_startup_notices(self) -> None:
        notice = self.controller.webdav_startup_notice
        if not notice:
            return
        icon = QSystemTrayIcon.MessageIcon.Warning if "не удалось" in notice.lower() else QSystemTrayIcon.MessageIcon.Information
        shown = False
        if self.tray_available and hasattr(self, "tray") and self.tray.isVisible():
            self._show_tray_message(APP_TITLE_BASE, notice, icon=icon, timeout=8000)
            shown = True
        if not shown:
            QMessageBox.information(self, APP_TITLE_BASE, notice)
        clear_webdav_pending_notice()
        self.controller.webdav_startup_notice = None

    def _load_fonts(self) -> None:
        """Register bundled fonts (if any) and resolve Inter / Roboto Mono."""
        import os

        fonts_dir = os.path.join(os.path.dirname(__file__), "assets", "fonts")
        if os.path.isdir(fonts_dir):
            for name in os.listdir(fonts_dir):
                if name.lower().endswith((".ttf", ".otf")):
                    QFontDatabase.addApplicationFont(os.path.join(fonts_dir, name))

        families = set(QFontDatabase.families())

        def pick(*candidates: str) -> str:
            for family in candidates:
                if family in families:
                    return family
            return candidates[-1]

        self._sans_family = pick(
            "Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial"
        )
        self._mono_family = pick(
            "Roboto Mono", "SF Mono", "Menlo", "Consolas", "Cascadia Mono", "Courier New"
        )
        app_font = QFont(self._sans_family, 10)
        app_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.app.setFont(app_font)

    @staticmethod
    def _freeze_toolbar_button_width(button: QPushButton) -> None:
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.setFixedWidth(button.sizeHint().width())

    def _freeze_add_task_button_width(self) -> None:
        self._add_task_button.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._add_task_button.setFixedWidth(
            self._add_task_button.sizeHint().width() + ADD_TASK_BUTTON_EXTRA_WIDTH
        )

    def _freeze_summary_label_width(self) -> None:
        metrics = self.today_total_label.fontMetrics()
        sample_width = metrics.horizontalAdvance(SUMMARY_LABEL_SAMPLE) + 12
        text_width = metrics.horizontalAdvance(self.today_total_label.text()) + 12
        width = max(sample_width, text_width)
        self.today_total_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.today_total_label.setFixedWidth(width)

    def _sync_timer_digits_min_height(self) -> None:
        font = QFont(self._mono_family, TIMER_DIGITS_FONT_SIZE)
        font.setWeight(QFont.Weight.Light)
        metrics = QFontMetrics(font)
        sample_height = metrics.boundingRect("00:00:00").height()
        height = sample_height + TIMER_DIGITS_VERTICAL_PAD
        self.timer_digits.setFixedHeight(height)
        self.timer_digits.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

    def _timer_card_inner_width(self) -> int:
        return max(self.timer_card.width() - TIMER_CARD_HORIZONTAL_INSET, 120)

    def _reset_timer_task_name_constraints(self) -> None:
        self.active_task_name.setMinimumHeight(0)
        self.active_task_name.setMaximumHeight(16777215)
        self.active_task_name.setMinimumWidth(0)
        self.active_task_name.setMaximumWidth(16777215)

    def _fit_timer_task_name(self, title: str) -> None:
        if not title.strip():
            self._reset_timer_task_name_constraints()
            return
        display_text = break_long_unbroken_runs(title)
        fit_wrapped_label_height(
            self.active_task_name,
            display_text,
            width=self._timer_card_inner_width(),
        )

    def _relayout_timer_card(self) -> None:
        card_layout = self.timer_card.layout()
        panel_layout = self.timer_panel.layout()
        if card_layout is None or panel_layout is None:
            return
        card_layout.invalidate()
        card_layout.activate()
        card_height = self.timer_card.sizeHint().height()
        self.timer_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.timer_card.setFixedHeight(card_height)
        self._sync_focus_section_height()
        panel_layout.invalidate()
        panel_layout.activate()
        self.timer_panel.updateGeometry()
        self.timer_card.updateGeometry()
        self._update_main_window_min_height()

    def _main_window_min_height(self) -> int:
        self._sync_focus_section_height()
        panel_height = self.timer_panel.sizeHint().height()
        menu_height = (
            self.menuBar().height()
            if self.menuBar() is not None
            else WINDOW_VERTICAL_CHROME
        )
        return max(WINDOW_MIN_HEIGHT, panel_height + menu_height + 4)

    def _update_main_window_min_height(self) -> None:
        min_height = self._main_window_min_height()
        if self.minimumHeight() != min_height:
            self.setMinimumHeight(min_height)

    def _sync_focus_section_height(self) -> None:
        focus_layout = self.focus_card.layout()
        panel_layout = self.timer_panel.layout()
        if focus_layout is None or panel_layout is None:
            return
        focus_layout.invalidate()
        focus_layout.activate()
        height = self.focus_card.sizeHint().height()
        self.focus_card.setMinimumHeight(height)
        self.focus_section.setMinimumHeight(height)

    def _apply_window_constraints(self) -> None:
        """Keep toolbar labels intact and block layouts that clip task titles."""
        for button in self._view_buttons.values():
            self._freeze_toolbar_button_width(button)
        self._freeze_toolbar_button_width(self._portal_button)
        self._freeze_add_task_button_width()
        self._freeze_summary_label_width()
        self._sync_timer_digits_min_height()

        subbar_min = self._subbar.minimumSizeHint().width()
        tasks_min = max(subbar_min, TASK_LIST_MIN_WIDTH)
        self.tasks_page.setMinimumWidth(tasks_min)
        self._update_main_window_min_height()
        self.setMinimumWidth(
            SIDEBAR_WIDTH + RIGHT_COLUMN_WIDTH + tasks_min,
        )

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("rootArea")
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())

        self.tasks_page = self._build_tasks_page()

        main_area = QWidget()
        main_area.setObjectName("mainArea")
        main_layout = QHBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.tasks_page, 1)
        self.right_column = self._build_right_column()
        main_layout.addWidget(self.right_column, 0, Qt.AlignmentFlag.AlignTop)
        root_layout.addWidget(main_area, 1)

        self.setCentralWidget(central)
    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(52)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(2)

        logo = QLabel("⏱")
        logo.setObjectName("sidebarLogo")
        logo.setFixedSize(32, 32)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)

        tasks_button = QPushButton("≣")
        tasks_button.setObjectName("navButton")
        tasks_button.setFixedSize(38, 38)
        tasks_button.setToolTip("Задачи")
        tasks_button.setProperty("active", True)
        tasks_button.setEnabled(False)
        layout.addWidget(tasks_button, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        settings_button = QPushButton("⚙")
        settings_button.setObjectName("navButton")
        settings_button.setFixedSize(38, 38)
        settings_button.setToolTip("Настройки")
        settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_button.clicked.connect(self._open_settings)
        layout.addWidget(settings_button, 0, Qt.AlignmentFlag.AlignHCenter)

        return bar

    def _build_tasks_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("tasksPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # ── Subbar: filter chips, date, portal, new task ───────
        subbar = QFrame()
        subbar.setObjectName("subbar")
        subbar.setFixedHeight(48)
        self._subbar = subbar
        sub = QHBoxLayout(subbar)
        sub.setContentsMargins(20, 0, 20, 0)
        sub.setSpacing(6)

        self._view_buttons: dict[str, QPushButton] = {}
        for key, label in (("plan", "Сегодня"), ("in_progress", "В работе"), ("all", "Все")):
            chip = QPushButton(label)
            chip.setObjectName("filterChip")
            chip.setFixedHeight(28)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, view=key: self._set_view(view))
            self._view_buttons[key] = chip
            sub.addWidget(chip)

        self.date_edit = QDateEdit()
        self.date_edit.setObjectName("dateFilter")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setFixedWidth(124)
        self.date_edit.setToolTip("Показать задачи с затраченным временем за выбранный день")
        _style_calendar_field(self.date_edit)
        self.date_edit.blockSignals(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.blockSignals(False)
        self.date_edit.dateChanged.connect(self._set_date)
        self.date_edit.calendarWidget().clicked.connect(self._set_date)
        sub.addWidget(self.date_edit)

        sub.addStretch(1)

        self.today_total_label = QLabel("")
        self.today_total_label.setObjectName("summaryLabel")
        self.today_total_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        sub.addWidget(self.today_total_label)

        webdav_pull_button = QPushButton("↓ Скачать")
        webdav_pull_button.setObjectName("ghostButton")
        webdav_pull_button.setFixedHeight(28)
        webdav_pull_button.setCursor(Qt.CursorShape.PointingHandCursor)
        webdav_pull_button.setToolTip("Скачать data.json с WebDAV и объединить с локальной базой")
        webdav_pull_button.clicked.connect(self._webdav_pull_now_main)
        self._webdav_pull_button = webdav_pull_button
        sub.addWidget(webdav_pull_button)

        webdav_push_button = QPushButton("↑ Загрузить")
        webdav_push_button.setObjectName("ghostButton")
        webdav_push_button.setFixedHeight(28)
        webdav_push_button.setCursor(Qt.CursorShape.PointingHandCursor)
        webdav_push_button.setToolTip("Загрузить локальную базу на WebDAV (с предварительным слиянием)")
        webdav_push_button.clicked.connect(self._webdav_push_now_main)
        self._webdav_push_button = webdav_push_button
        sub.addWidget(webdav_push_button)

        portal_button = QPushButton("С портала")
        portal_button.setObjectName("ghostButton")
        portal_button.setFixedHeight(28)
        portal_button.setCursor(Qt.CursorShape.PointingHandCursor)
        portal_button.clicked.connect(self._open_portal_import)
        self._portal_button = portal_button
        sub.addWidget(portal_button)

        add_button = QPushButton("＋ Новая задача")
        add_button.setObjectName("btnAccent")
        add_button.setFixedHeight(30)
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self._open_create_dialog)
        self._add_task_button = add_button
        sub.addWidget(add_button)

        page_layout.addWidget(subbar)

        # ── Content row: task list + dark timer panel ──────────
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("taskScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.days_container = QWidget()
        self.days_container.setObjectName("taskListBg")
        self.days_container.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.days_layout = QVBoxLayout(self.days_container)
        self.days_layout.setContentsMargins(20, 12, 20, 16)
        self.days_layout.setSpacing(6)
        self.days_layout.addStretch(1)
        self.scroll_area.setWidget(self.days_container)
        content_layout.addWidget(self.scroll_area, 1)

        page_layout.addWidget(content, 1)
        return page

    def _build_right_column(self) -> QWidget:
        column = QWidget()
        column.setObjectName("rightColumn")
        column.setFixedWidth(268)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._build_timer_panel())
        layout.addStretch(1)
        return column

    def _build_timer_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("timerPanel")
        panel.setMinimumWidth(268)
        panel.setMaximumWidth(268)
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.timer_panel = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 20, 18, 20)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        timer_label = QLabel("ТАЙМЕР")
        timer_label.setObjectName("timerLbl")
        layout.addWidget(timer_label)
        layout.addSpacing(12)

        self.timer_card = QFrame()
        self.timer_card.setObjectName("timerCard")
        self.timer_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )
        card = QVBoxLayout(self.timer_card)
        card.setContentsMargins(14, 14, 14, 14)
        card.setSpacing(0)

        self.active_task_name = QLabel("Выберите задачу\nи нажмите Старт")
        self.active_task_name.setObjectName("tcardName")
        self.active_task_name.setWordWrap(True)
        card.addWidget(self.active_task_name)
        card.addSpacing(14)

        self.timer_digits = QLabel("00:00:00")
        self.timer_digits.setObjectName("timerDigits")
        self.timer_digits.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        card.addWidget(self.timer_digits)
        card.addSpacing(TIMER_CARD_STATS_SPACING)

        sub = QHBoxLayout()
        sub.setSpacing(16)
        for caption, attr in (("СЕГОДНЯ", "timer_today_value"), ("ВСЕГО", "timer_total_value")):
            box = QVBoxLayout()
            box.setSpacing(1)
            cap = QLabel(caption)
            cap.setObjectName("tcsLbl")
            box.addWidget(cap)
            value = QLabel("0:00")
            value.setObjectName("tcsVal")
            setattr(self, attr, value)
            box.addWidget(value)
            sub.addLayout(box)
        sub.addStretch(1)
        card.addLayout(sub)

        layout.addWidget(self.timer_card)
        layout.addSpacing(16)

        self.timer_progress = QProgressBar()
        self.timer_progress.setObjectName("timerProgress")
        self.timer_progress.setTextVisible(False)
        self.timer_progress.setFixedHeight(3)
        self.timer_progress.setRange(0, 100)
        self.timer_progress.setValue(0)
        layout.addWidget(self.timer_progress)
        layout.addSpacing(16)

        self.stop_active_button = QPushButton("Стоп")
        self.stop_active_button.setObjectName("btnStop")
        self.stop_active_button.setFixedHeight(38)
        self.stop_active_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_active_button.clicked.connect(self._stop_active)
        layout.addWidget(self.stop_active_button)
        layout.addSpacing(6)

        self.complete_active_button = QPushButton("Завершить задачу")
        self.complete_active_button.setObjectName("btnComplete")
        self.complete_active_button.setFixedHeight(38)
        self.complete_active_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.complete_active_button.clicked.connect(self._complete_active)
        layout.addWidget(self.complete_active_button)

        layout.addSpacing(12)
        self.focus_section = self._build_focus_section()
        layout.addWidget(self.focus_section)

        return panel

    def _build_focus_section(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("focusPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        self.focus_card = QFrame()
        self.focus_card.setObjectName("focusCard")
        self.focus_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        focus_layout = QVBoxLayout(self.focus_card)
        focus_layout.setContentsMargins(14, 16, 14, 16)
        focus_layout.setSpacing(12)
        focus_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        focus_title = QLabel("РЕЖИМ КОНЦЕНТРАЦИИ")
        focus_title.setObjectName("focusHeading")
        focus_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_layout.addWidget(focus_title, 0, Qt.AlignmentFlag.AlignHCenter)

        self.focus_display = QLabel("20:00")
        self.focus_display.setObjectName("focusDisplay")
        self.focus_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_layout.addWidget(self.focus_display, 0, Qt.AlignmentFlag.AlignHCenter)

        self.focus_status_label = QLabel("Готов к запуску")
        self.focus_status_label.setObjectName("focusStatusLabel")
        self.focus_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_layout.addWidget(self.focus_status_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self.focus_buttons: dict[int, QPushButton] = {}
        preset_wrap = QWidget()
        preset_wrap.setObjectName("focusPresetWrap")
        preset_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        preset_layout = QVBoxLayout(preset_wrap)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(FOCUS_PRESET_ROW_SPACING)
        preset_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        preset_rows = 0
        for row_minutes in ((5, 10, 20), (30, 40)):
            row = QHBoxLayout()
            row.setSpacing(5)
            row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            for minutes in row_minutes:
                button = QPushButton(f"{minutes} мин")
                button.setObjectName("focusDur")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFixedHeight(FOCUS_PRESET_BUTTON_HEIGHT)
                button.setSizePolicy(
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
                button.clicked.connect(
                    lambda _checked=False, value=minutes: self._start_focus_timer(value)
                )
                self.focus_buttons[minutes] = button
                row.addWidget(button)
            preset_layout.addLayout(row)
            preset_rows += 1
        preset_wrap.setMinimumHeight(
            preset_rows * FOCUS_PRESET_BUTTON_HEIGHT
            + max(0, preset_rows - 1) * FOCUS_PRESET_ROW_SPACING
        )
        focus_layout.addWidget(preset_wrap, 0, Qt.AlignmentFlag.AlignHCenter)

        self.focus_stop_button = QPushButton("Остановить таймер")
        self.focus_stop_button.setObjectName("focusGo")
        self.focus_stop_button.setFixedHeight(38)
        self.focus_stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.focus_stop_button.clicked.connect(self._stop_focus_timer)
        focus_layout.addWidget(self.focus_stop_button)

        panel_layout.addWidget(self.focus_card)
        return panel

    def _build_menu_bar(self) -> None:
        bar = self.menuBar()
        if sys.platform != "darwin":
            bar.setNativeMenuBar(False)

        settings_menu = bar.addMenu("Настройки")
        settings_action = QAction("Параметры…", self)
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)

        merge_legacy_action = QAction("Объединить базы старых версий…", self)
        merge_legacy_action.triggered.connect(self._merge_legacy_bases)
        settings_menu.addAction(merge_legacy_action)

        legacy_path_action = QAction("Указать каталог старой версии…", self)
        legacy_path_action.triggered.connect(self._configure_legacy_data_path)
        settings_menu.addAction(legacy_path_action)

        legacy_paths_action = QAction("Каталоги старых версий…", self)
        legacy_paths_action.triggered.connect(self._manage_legacy_data_paths)
        settings_menu.addAction(legacy_paths_action)

        exit_action = QAction("Выход", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self._request_exit)
        bar.addAction(exit_action)

        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._open_about)
        bar.addAction(about_action)

    def _refresh_app_icon(self) -> None:
        clear_tray_app_icon_cache()
        self.app_icon = build_tray_app_icon(self.style())
        self.setWindowIcon(self.app_icon)
        if hasattr(self, "tray") and self.tray_available:
            self.tray.setIcon(self.app_icon)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app_icon, self)
        if not self.tray_available:
            return
        tray_menu = QMenu()

        show_action = QAction("Открыть", self)
        show_action.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(show_action)

        show_widget_action = QAction("Показать виджет", self)
        show_widget_action.triggered.connect(self._show_floating_from_tray)
        tray_menu.addAction(show_widget_action)

        settings_action = QAction("Настройки…", self)
        settings_action.triggered.connect(self._open_settings)
        tray_menu.addAction(settings_action)

        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._open_about)
        tray_menu.addAction(about_action)

        tray_menu.addSeparator()

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self._request_exit)
        tray_menu.addAction(exit_action)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._handle_tray_activation)
        self.tray.show()
        self._update_tray_tooltip()

    def _apply_styles(self) -> None:
        qss = """
            /* ── Base ─────────────────────────────────────── */
            QWidget { background: #F2F3F7; color: #252835; font-family: "__SANS__"; }
            QMainWindow, QWidget#rootArea, QWidget#tasksPage { background: #F2F3F7; }
            QLabel { background: transparent; }
            QToolTip {
                background: #252835; color: #FFFFFF; border: none;
                padding: 4px 8px; border-radius: 6px;
            }

            /* ── Generic inputs (dialogs) ─────────────────── */
            QLineEdit, QPlainTextEdit, QListWidget, QDateTimeEdit {
                background: #F5F6FA; border: 1px solid #D0D2D8; border-radius: 10px;
                padding: 8px 12px; color: #252835; selection-background-color: #3B83F6;
            }
            QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus,
            QDateTimeEdit:focus { border-color: #3B83F6; background: #FFFFFF; }
            QSpinBox {
                background: #F5F6FA; border: 1px solid #D0D2D8; border-radius: 10px;
                padding: 8px 28px 8px 12px; color: #252835; min-height: 20px;
            }
            QSpinBox:focus { border-color: #3B83F6; background: #FFFFFF; }
            QSpinBox::up-button, QSpinBox::down-button {
                subcontrol-origin: border; width: 24px; background: #ECEEF3;
                border: none; border-left: 1px solid #D0D2D8;
            }
            QSpinBox::up-button {
                subcontrol-position: top right; border-top-right-radius: 9px;
            }
            QSpinBox::down-button {
                subcontrol-position: bottom right; border-bottom-right-radius: 9px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #E2E5EB; }
            QSpinBox::up-arrow {
                width: 0; height: 0;
                border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-bottom: 5px solid #828B9A;
            }
            QSpinBox::down-arrow {
                width: 0; height: 0;
                border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-top: 5px solid #828B9A;
            }

            /* ── Generic buttons (dialogs / fallback) ─────── */
            QPushButton {
                background: #F5F6FA; border: 1px solid #D0D2D8; border-radius: 8px;
                padding: 7px 14px; color: #252835; font-weight: 400;
            }
            QPushButton:hover { background: #ECEEF3; }
            QPushButton:disabled { color: #B8BDC9; }
            QPushButton#primaryButton {
                background: #3B83F6; border: none; color: #FFFFFF; font-weight: 500;
                padding: 8px 20px;
            }
            QPushButton#btnAccent {
                background: #3B83F6; border: none; color: #FFFFFF; font-weight: 500;
                padding: 0 16px;
            }
            QPushButton#primaryButton:hover, QPushButton#btnAccent:hover { background: #2563EB; }
            QPushButton#ghostButton {
                background: transparent; border: 1px solid #D0D2D8; border-radius: 8px;
                color: #828B9A; padding: 0 14px; font-weight: 400;
            }
            QPushButton#ghostButton:hover { background: #F5F6FA; color: #252835; }
            QPushButton#deleteGhostButton {
                background: transparent; border: none; border-radius: 7px;
                padding: 4px 6px; color: #828B9A;
            }
            QPushButton#deleteGhostButton:hover { background: #FDE8E8; color: #E05353; }

            /* ── Sidebar ──────────────────────────────────── */
            QFrame#sidebar { background: #FFFFFF; border-right: 1px solid #DCDEE3; }
            QLabel#sidebarLogo {
                background: #3B83F6; color: #FFFFFF; border-radius: 10px;
                font-size: 17px; font-weight: 600;
            }
            QPushButton#navButton {
                background: transparent; border: none; border-radius: 10px;
                color: #B8BDC9; font-size: 18px; padding: 0;
            }
            QPushButton#navButton:hover { background: #F5F6FA; color: #828B9A; }
            QPushButton#navButton[active="true"] { background: #E8F0FD; color: #3B83F6; }

            /* ── Subbar ───────────────────────────────────── */
            QFrame#subbar { background: #FFFFFF; border-bottom: 1px solid #DCDEE3; }
            QPushButton#filterChip {
                background: #F5F6FA; border: 1px solid transparent; border-radius: 8px;
                color: #828B9A; padding: 0 13px; font-size: 12px; font-weight: 400;
            }
            QPushButton#filterChip:hover { background: #FFFFFF; color: #828B9A; }
            QPushButton#filterChip[active="true"] {
                background: #FFFFFF; border: 1px solid #D0D2D8; color: #3B83F6; font-weight: 500;
            }
            QLabel#summaryLabel { color: #B8BDC9; font-size: 11px; }

            /* ── Task list ────────────────────────────────── */
            QScrollArea#taskScroll { background: #F2F3F7; border: none; }
            QWidget#taskListBg { background: #F2F3F7; }
            QScrollBar:vertical { width: 6px; background: transparent; margin: 2px; }
            QScrollBar::handle:vertical { background: #D0D2D8; border-radius: 3px; min-height: 24px; }
            QScrollBar::handle:vertical:hover { background: #B8BDC9; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

            /* ── Task row ─────────────────────────────────── */
            QFrame#taskRow {
                background: #FFFFFF; border: 1px solid #DCDEE3; border-radius: 10px;
            }
            QFrame#taskRow:hover { border-color: #D0D2D8; }
            QFrame#taskRow[status="running"] {
                border: 1px solid rgba(39,174,96,0.45); border-left: 3px solid #27AE60;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(39,174,96,0.10), stop:0.52 #FFFFFF);
            }
            QFrame#taskRow[status="paused"] { border-color: rgba(224,123,53,0.40); }
            QFrame#taskDot { border-radius: 4px; }
            QFrame#taskDot[status="running"] { background: #27AE60; }
            QFrame#taskDot[status="paused"]  { background: #E07B35; }
            QFrame#taskDot[status="todo"]    { background: transparent; border: 1px solid #B8BDC9; }
            QFrame#taskDot[status="done"]    { background: #B8BDC9; }
            QLabel#taskName { color: #252835; font-size: 13px; }
            QFrame#taskRow[status="done"] QLabel#taskName {
                color: #B8BDC9; text-decoration: line-through;
            }
            QLabel#rowTimeLbl { color: #B8BDC9; font-size: 10px; }
            QLabel#rowTimeSep { color: #D0D2D8; font-size: 11px; }
            QLabel#rowTimeVal { color: #828B9A; font-size: 11px; font-family: "__MONO__"; }
            QLabel#rowTimeVal[live="true"] { color: #27AE60; }
            QLabel#taskRowDesc { color: #828B9A; font-size: 12px; }
            QLabel#taskRowDesc[empty="true"] { color: #B8BDC9; font-style: italic; }
            QWidget#taskRowMetaBox { background: transparent; }
            QLabel#taskRowMetaLbl { color: #828B9A; font-size: 11px; }
            QLabel#taskRowMetaVal {
                background: #F5F6FA; border: 1px solid #DCDEE3; border-radius: 4px;
                color: #252835; font-size: 11px; padding: 2px 6px;
            }
            QLabel#taskRowMetaVal[empty="true"] { color: #B8BDC9; }
            QWidget#taskRowPinnedFooter { background: transparent; }

            QWidget#rowActions { background: transparent; }
            QFrame#rowActionsFade {
                border: none;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255,255,255,0), stop:1 rgba(255,255,255,255));
            }
            QPushButton#iconAction, QPushButton#iconActionDanger {
                background: transparent; border: none; border-radius: 7px;
                color: #B8BDC9; font-size: 14px; padding: 0;
            }
            QPushButton#iconAction:hover { background: #F5F6FA; color: #828B9A; }
            QPushButton#iconActionDanger:hover { background: #FDE8E8; color: #E05353; }
            QPushButton#linkAction {
                background: transparent; border: none; border-radius: 7px;
                color: #828B9A; font-size: 11px; padding: 0 9px;
            }
            QPushButton#linkAction:hover { background: #F5F6FA; color: #252835; }
            QPushButton#rowStart {
                background: #27AE60; border: none; border-radius: 7px;
                color: #FFFFFF; font-size: 11px; font-weight: 500; padding: 0 11px;
            }
            QPushButton#rowStart:hover { background: #22994F; }
            QPushButton#rowStop {
                background: #FDE8E8; border: 1px solid rgba(224,83,83,0.25); border-radius: 7px;
                color: #E05353; font-size: 11px; font-weight: 500; padding: 0 11px;
            }
            QPushButton#rowStop:hover { background: #FBD9D9; }
            QPushButton#rowResume {
                background: #E8F0FD; border: none; border-radius: 7px;
                color: #3B83F6; font-size: 11px; font-weight: 500; padding: 0 11px;
            }
            QPushButton#rowResume:hover { background: #DBE8FC; }

            /* ── Timer panel (light) ──────────────────────── */
            QFrame#timerPanel {
                background: #ECEEF3; border-left: 1px solid #DCDEE3;
            }
            QFrame#timerPanel[running="true"] { border-left: 1px solid rgba(39,174,96,0.35); }
            QLabel#timerLbl {
                color: #B8BDC9; font-size: 10px; font-weight: 500;
                letter-spacing: 1px;
            }
            QFrame#timerCard {
                background: #FFFFFF; border: 1px solid #DCDEE3;
                border-radius: 12px;
            }
            QFrame#timerCard[running="true"] {
                background: #F0FAF4; border: 1px solid rgba(39,174,96,0.30);
            }
            QLabel#tcardName { color: #252835; font-size: 13px; font-weight: 500; }
            QLabel#timerDigits {
                color: #3B83F6; font-family: "__MONO__"; font-size: 38px; font-weight: 300;
            }
            QFrame#timerPanel[running="true"] QLabel#timerDigits { color: #27AE60; }
            QLabel#tcsLbl {
                color: #B8BDC9; font-size: 9px; font-weight: 500; letter-spacing: 1px;
            }
            QLabel#tcsVal { color: #828B9A; font-family: "__MONO__"; font-size: 12px; }
            QFrame#timerPanel[running="true"] QLabel#tcsVal { color: #27AE60; }
            QProgressBar#timerProgress {
                background: #DCDEE3; border: none; border-radius: 2px;
            }
            QProgressBar#timerProgress::chunk { background: #27AE60; border-radius: 2px; }
            QPushButton#btnStop {
                background: #FFFFFF; border: 1px solid #D0D2D8;
                border-radius: 10px; color: #252835; font-weight: 500;
            }
            QPushButton#btnStop:hover { background: #F5F6FA; }
            QPushButton#btnStop:disabled { color: #B8BDC9; }
            QPushButton#btnComplete {
                background: #FDE8E8; border: 1px solid #F5C4C4;
                border-radius: 10px; color: #E05353; font-weight: 500;
            }
            QPushButton#btnComplete:hover { background: #FBD0D0; }
            QPushButton#btnComplete:disabled { color: #E8A8A8; }

            /* ── Focus card (under timer) ────────────────── */
            QFrame#focusPanel { background: transparent; }
            QFrame#focusCard {
                background: #FFFFFF; border: 1px solid #DCDEE3; border-radius: 12px;
            }
            QWidget#focusPresetWrap { background: transparent; }
            QLabel#focusHeading {
                color: #B8BDC9; font-size: 10px; font-weight: 500; letter-spacing: 1.5px;
            }
            QLabel#focusDisplay {
                color: #3B83F6; font-family: "__MONO__"; font-size: 44px; font-weight: 300;
            }
            QLabel#focusDisplay[done="true"] { color: #27AE60; }
            QLabel#focusStatusLabel { color: #B8BDC9; font-size: 11px; }
            QPushButton#focusDur {
                background: #F5F6FA; border: 1px solid #D0D2D8; border-radius: 10px;
                color: #828B9A; padding: 5px 7px; font-size: 12px; min-width: 0;
                min-height: 24px;
            }
            QPushButton#focusDur:hover { background: #ECEEF3; }
            QPushButton#focusDur[active="true"] {
                background: #3B83F6; border: 1px solid #3B83F6; color: #FFFFFF; font-weight: 500;
            }
            QPushButton#focusGo {
                background: #FFFFFF; border: 1px solid #D0D2D8; border-radius: 10px;
                color: #828B9A; font-weight: 500; letter-spacing: 1px;
            }
            QPushButton#focusGo:hover { background: #ECEEF3; color: #252835; }
            QPushButton#focusGo:disabled { color: #B8BDC9; }


            /* ── Menu bar (link B24) ──────────────────────── */
            QMenuBar {
                background: #F2F3F7; color: #252835; padding: 4px 10px; spacing: 4px;
            }
            QMenuBar::item {
                background: transparent; padding: 6px 12px; border-radius: 8px;
            }
            QMenuBar::item:selected { background: rgba(37, 40, 53, 0.08); }
            QMenu {
                background: #FFFFFF; border: 1px solid rgba(37, 40, 53, 0.12);
                border-radius: 10px; padding: 4px;
            }
            QMenu::item { padding: 8px 24px 8px 12px; border-radius: 6px; }
            QMenu::item:selected { background: rgba(37, 40, 53, 0.08); }
            /* ── Dialogs ──────────────────────────────────── */
            QDialog { background: #FFFFFF; }
            QLabel#sectionTitle { color: #252835; font-size: 15px; font-weight: 500; }
            QLabel#descriptionLabel { color: #828B9A; font-size: 12px; }

            /* Checkboxes */
            QCheckBox { color: #252835; spacing: 8px; }
            QCheckBox::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid #D0D2D8; background: #FFFFFF;
            }
            QCheckBox::indicator:hover { border-color: #3B83F6; }
            QCheckBox::indicator:checked {
                background: #3B83F6; border-color: #3B83F6; image: url("__CHECK__");
            }

            /* Tables (history) */
            QTableWidget, QTableView {
                background: #FFFFFF; border: 1px solid #DCDEE3; border-radius: 10px;
                alternate-background-color: #FAFBFC; outline: none;
                selection-background-color: #E8F0FD; selection-color: #252835;
            }
            QTableView::item { padding: 4px 8px; border: none; }
            QTableView::item:selected { background: #E8F0FD; color: #252835; }
            QTableView::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid #D0D2D8; background: #FFFFFF;
            }
            QTableView::indicator:hover { border-color: #3B83F6; }
            QTableView::indicator:checked {
                background: #3B83F6; border-color: #3B83F6; image: url("__CHECK__");
            }
            QHeaderView { background: transparent; }
            QHeaderView::section {
                background: #F5F6FA; color: #828B9A; padding: 8px 8px;
                border: none; border-bottom: 1px solid #DCDEE3;
                font-size: 11px; font-weight: 500;
            }
            QHeaderView::section:first { border-top-left-radius: 10px; }
            QHeaderView::section:last { border-top-right-radius: 10px; }
            QTableCornerButton::section { background: #F5F6FA; border: none; }

            /* Destructive ghost button (Удалить запись) */
            QPushButton#deleteGhostButton {
                background: transparent; border: 1px solid rgba(224,83,83,0.30);
                border-radius: 8px; padding: 0 14px; color: #E05353; font-weight: 400;
            }
            QPushButton#deleteGhostButton:hover { background: #FDE8E8; }
            QPushButton#deleteGhostButton:disabled { color: #E0A8A8; border-color: #F1D6D6; }
            QPushButton#ghostButton:disabled { color: #C8CCD4; border-color: #E4E6EC; }

            QTabWidget::pane { border: 1px solid #DCDEE3; border-radius: 10px; top: -1px; }
            QTabBar::tab {
                background: #F5F6FA; color: #828B9A; padding: 7px 16px;
                margin-right: 4px; border-radius: 8px; font-weight: 500;
            }
            QTabBar::tab:selected { background: #3B83F6; color: #FFFFFF; }
            QProgressBar {
                background: #E4E6EC; border: none; border-radius: 3px; text-align: center;
                color: #828B9A;
            }
            QProgressBar::chunk { background: #3B83F6; border-radius: 3px; }
        """
        qss = (
            qss.replace("__SANS__", self._sans_family)
            .replace("__MONO__", self._mono_family)
            .replace("__CHECK__", _check_icon_path().replace("\\", "/"))
        )
        self.setStyleSheet(qss)
    def refresh_ui(self) -> None:
        for key, button in self._view_buttons.items():
            button.setProperty("active", key == self._current_view)
            button.style().unpolish(button)
            button.style().polish(button)

        reference_date = self._selected_date if self._current_view == "date" else None
        if reference_date:
            self.today_total_label.setText(
                f"За {format_day_label(reference_date)} всего: "
                f"{format_hm(self.controller.today_total_seconds(reference_date))}"
            )
        else:
            self.today_total_label.setText(
                f"Сегодня всего: {format_hm(self.controller.today_total_seconds())}"
            )
        self._freeze_summary_label_width()

        while self.days_layout.count():
            item = self.days_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._task_rows.clear()
        self._task_rows_reference_date = reference_date

        if self._current_view == "plan":
            tasks = self.controller.tasks_today_plan()
        elif self._current_view == "in_progress":
            tasks = self.controller.tasks_in_progress()
        elif self._current_view == "date":
            tasks = self.controller.tasks_on_date(reference_date)
        else:
            tasks = self.controller.tasks_all()

        # Completed tasks sink to the bottom (stable: keeps prior order otherwise).
        tasks = sorted(tasks, key=lambda t: t.status == TaskStatus.COMPLETED)

        if not tasks:
            hint = QLabel(self._empty_hint())
            hint.setObjectName("descriptionLabel")
            hint.setWordWrap(True)
            self.days_layout.addWidget(hint)
        else:
            for task in tasks:
                row = TaskRow(self.controller, task, reference_date=reference_date)
                row.start_requested.connect(self._start_task)
                row.stop_requested.connect(self._stop_task)
                row.complete_requested.connect(self._confirm_complete_task)
                row.resume_requested.connect(self._resume_task)
                row.history_requested.connect(self._open_history)
                row.edit_requested.connect(self._open_task_edit)
                row.row_selected.connect(self._on_task_row_selected)
                row.row_deselected.connect(self._on_task_row_deselected)
                row.delete_requested.connect(self._confirm_delete_task)
                row.plan_toggle_requested.connect(self._toggle_plan)
                self._task_rows[task.id] = row
                self.days_layout.addWidget(row)
            if self._pinned_task_row_id in self._task_rows:
                self._task_rows[self._pinned_task_row_id].set_pinned(True)
        self.days_layout.addStretch(1)
        self._refresh_task_row_layouts()
        self._refresh_active_panel()
        self._refresh_focus_panel()

    def _refresh_task_row_layouts(self) -> None:
        for row in self._task_rows.values():
            row.refresh_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_task_row_layouts()

    def _update_task_row_times(self) -> None:
        """Update row durations on the clock tick without rebuilding the list."""
        if not self._task_rows:
            return
        reference_date = self._task_rows_reference_date
        for task_id, row in self._task_rows.items():
            try:
                task = self.controller.find_task(task_id)
            except KeyError:
                continue
            row.update_times(self.controller, task, reference_date)
    def _empty_hint(self) -> str:
        if self._current_view == "plan":
            return (
                "В плане на сегодня пусто. Добавь задачи кнопкой «В план» "
                "в фильтрах «В работе» или «Все»."
            )
        if self._current_view == "in_progress":
            return "Нет незавершённых задач."
        if self._current_view == "date" and self._selected_date:
            return f"Нет задач с затраченным временем за {format_day_label(self._selected_date)}."
        return "Пока нет задач."
    def _set_timer_running(self, running: bool) -> None:
        for widget in (self.timer_panel, self.timer_card):
            if bool(widget.property("running")) != running:
                widget.setProperty("running", running)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
    def _refresh_active_panel(self) -> None:
        panel_task = self.controller.timer_panel_task()
        timer_running = (
            panel_task is not None
            and panel_task.status == TaskStatus.RUNNING
            and panel_task.active_session() is not None
        )
        self._set_timer_running(timer_running)
        if not panel_task:
            self._reset_timer_task_name_constraints()
            self.active_task_name.setText("Выберите задачу\nи нажмите Старт")
            self.timer_digits.setText("00:00:00")
            self.timer_today_value.setText("0:00")
            self.timer_total_value.setText("0:00")
            self.timer_progress.setValue(0)
            self.stop_active_button.setText("Стоп")
            self.stop_active_button.setEnabled(False)
            self.complete_active_button.setEnabled(False)
            self._relayout_timer_card()
            return
        now = datetime.now()
        total = panel_task.total_seconds(now)
        self._fit_timer_task_name(panel_task.title)
        self.timer_digits.setText(format_duration(total))
        self.timer_today_value.setText(format_hm(self.controller.today_seconds(panel_task)))
        self.timer_total_value.setText(format_hm(total))
        interval = max(1, self.controller.reminder_interval_minutes()) * 60
        session = panel_task.active_session()
        elapsed = session.duration_seconds(now) if session else 0
        self.timer_progress.setValue(int(min(elapsed / interval, 1.0) * 100))
        if timer_running:
            self.stop_active_button.setText("Стоп")
        else:
            self.stop_active_button.setText("Продолжить")
        self.stop_active_button.setEnabled(True)
        self.complete_active_button.setEnabled(True)
        self._relayout_timer_card()
    def _refresh_focus_panel(self) -> None:
        focus_state = self.controller.focus_timer_state()
        selected_minutes = int(focus_state.get("selected_minutes") or 20)
        remaining_seconds = self.controller.focus_remaining_seconds()

        if remaining_seconds > 0:
            minutes = remaining_seconds // 60
            seconds = remaining_seconds % 60
            self.focus_display.setText(f"{minutes:02d}:{seconds:02d}")
            self.focus_status_label.setText("Идет фокус-сессия")
            self.focus_stop_button.setEnabled(True)
            self._set_focus_done(False)
        else:
            self.focus_display.setText(f"{selected_minutes:02d}:00")
            self.focus_status_label.setText("Готов к запуску")
            self.focus_stop_button.setEnabled(False)
            self._set_focus_done(False)

        for minutes, button in self.focus_buttons.items():
            button.setProperty("active", minutes == selected_minutes)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _set_focus_done(self, done: bool) -> None:
        if bool(self.focus_display.property("done")) != done:
            self.focus_display.setProperty("done", done)
            self.focus_display.style().unpolish(self.focus_display)
            self.focus_display.style().polish(self.focus_display)
            self.focus_display.update()
    def _open_about(self) -> None:
        dialog = AboutDialog(self.controller, self)
        dialog.exec()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.controller, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.set_reminder_interval_minutes(dialog.reminder_spin.value())
            self.controller.set_bitrix_webhook(dialog.webhook_edit.text())
            self.controller.set_bitrix_portal_config(dialog.portal_config())
            save_webdav_settings(dialog.webdav_config())
            self._configure_webdav_periodic_timer()
            self.refresh_ui()

    def _configure_webdav_periodic_timer(self) -> None:
        config = load_webdav_config()
        if config.enabled and config.sync_interval_minutes > 0 and config.is_configured():
            self._webdav_periodic_timer.start(config.sync_interval_minutes * 60 * 1000)
        else:
            self._webdav_periodic_timer.stop()

    def _webdav_sync_running(self) -> bool:
        thread = self._webdav_main_sync_thread
        return thread is not None and thread.isRunning()

    def _set_webdav_buttons_enabled(self, enabled: bool) -> None:
        if hasattr(self, "_webdav_pull_button"):
            self._webdav_pull_button.setEnabled(enabled)
        if hasattr(self, "_webdav_push_button"):
            self._webdav_push_button.setEnabled(enabled)

    def _webdav_pull_now_main(self) -> None:
        config = load_webdav_config()
        if not config.is_configured():
            QMessageBox.warning(self, "WebDAV", "Укажите URL и имя пользователя в настройках WebDAV.")
            return
        if self._webdav_sync_running():
            return
        self.controller.save()
        self._set_webdav_buttons_enabled(False)

        def work() -> SyncOutcome:
            return pull_and_merge(self.controller.storage, config, require_enabled=False)

        self._webdav_main_sync_thread = _CallableThread(work, self)
        self._webdav_main_sync_thread.succeeded.connect(self._on_main_webdav_sync_ok)
        self._webdav_main_sync_thread.failed.connect(self._on_main_webdav_sync_failed)
        self._webdav_main_sync_thread.finished.connect(
            lambda: self._set_webdav_buttons_enabled(True)
        )
        self._webdav_main_sync_thread.start()

    def _webdav_push_now_main(self) -> None:
        config = load_webdav_config()
        if not config.is_configured():
            QMessageBox.warning(self, "WebDAV", "Укажите URL и имя пользователя в настройках WebDAV.")
            return
        if self._webdav_sync_running():
            return
        self.controller.save()
        self._set_webdav_buttons_enabled(False)

        def work() -> SyncOutcome:
            return push_local(self.controller.storage, config, require_enabled=False)

        self._webdav_main_sync_thread = _CallableThread(work, self)
        self._webdav_main_sync_thread.succeeded.connect(self._on_main_webdav_sync_ok)
        self._webdav_main_sync_thread.failed.connect(self._on_main_webdav_sync_failed)
        self._webdav_main_sync_thread.finished.connect(
            lambda: self._set_webdav_buttons_enabled(True)
        )
        self._webdav_main_sync_thread.start()

    def _webdav_periodic_sync(self) -> None:
        config = load_webdav_config()
        if not config.enabled or config.sync_interval_minutes <= 0 or not config.is_configured():
            self._webdav_periodic_timer.stop()
            return
        if self._webdav_sync_running() or self._webdav_remote_prompt_open:
            return
        check_thread = self._webdav_check_thread
        if check_thread is not None and check_thread.isRunning():
            return

        def work() -> RemoteCheckOutcome:
            return check_remote_changes(self.controller.storage, config, require_enabled=True)

        self._webdav_check_thread = _CallableThread(work, self)
        self._webdav_check_thread.succeeded.connect(self._on_webdav_remote_check_ok)
        self._webdav_check_thread.start()

    def _on_webdav_remote_check_ok(self, outcome: object) -> None:
        check = outcome if isinstance(outcome, RemoteCheckOutcome) else RemoteCheckOutcome()
        if check.error or not check.remote_changed:
            return
        config = load_webdav_config()
        if not should_show_remote_prompt(config, check.remote_hash):
            return
        if self._webdav_remote_prompt_open or self._webdav_sync_running():
            return
        config = prepare_remote_prompt(config, check.remote_hash)
        if self._tray_collapsed or not self.isVisible():
            self._restore_from_tray()
        self._webdav_remote_prompt_open = True
        answer = QMessageBox.question(
            self,
            "WebDAV",
            "На сервере обнаружены изменения с другого устройства. "
            "Скачать и объединить с локальной базой?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        self._webdav_remote_prompt_open = False
        if answer == QMessageBox.StandardButton.Yes:
            clear_pending_remote_remind(config)
            self._webdav_pull_after_remote_check()
        else:
            save_pending_remote_remind(config, check.remote_hash)

    def _webdav_pull_after_remote_check(self) -> None:
        config = load_webdav_config()
        if not config.is_configured() or self._webdav_sync_running():
            return
        self.controller.save()
        self._set_webdav_buttons_enabled(False)

        def work() -> SyncOutcome:
            return pull_and_merge(self.controller.storage, config, require_enabled=False)

        self._webdav_main_sync_thread = _CallableThread(work, self)
        self._webdav_main_sync_thread.succeeded.connect(self._on_main_webdav_sync_ok)
        self._webdav_main_sync_thread.failed.connect(self._on_main_webdav_sync_failed)
        self._webdav_main_sync_thread.finished.connect(
            lambda: self._set_webdav_buttons_enabled(True)
        )
        self._webdav_main_sync_thread.start()

    def _on_main_webdav_sync_ok(self, outcome: object) -> None:
        sync_outcome = outcome if isinstance(outcome, SyncOutcome) else SyncOutcome()
        if sync_outcome.state is not None:
            self.controller.state = sync_outcome.state
            self.controller.apply_loaded_state()
        else:
            self.controller.reload_state_from_storage()
        self.refresh_ui()
        if sync_outcome.error:
            QMessageBox.warning(self, "WebDAV", sync_outcome.error)
        elif sync_outcome.notice:
            self.controller.webdav_startup_notice = f"WebDAV: {sync_outcome.notice}"

    def _on_main_webdav_sync_failed(self, message: object) -> None:
        QMessageBox.warning(self, "WebDAV", str(message))

    def _merge_legacy_bases(self) -> None:
        from .legacy_merge_ui import offer_legacy_merge_manual

        if offer_legacy_merge_manual(self, resolve_app_title(), self.controller.storage):
            self.controller.reload_state_from_storage()
            self.refresh_ui()

    def _configure_legacy_data_path(self) -> None:
        from .legacy_merge_ui import configure_legacy_data_location

        configure_legacy_data_location(self, resolve_app_title())

    def _manage_legacy_data_paths(self) -> None:
        from .legacy_merge_ui import manage_legacy_data_locations

        manage_legacy_data_locations(self, resolve_app_title())

    def _open_create_dialog(self) -> None:
        self.create_dialog.open_clean()

    def _open_portal_import(self) -> None:
        dialog = PortalImportDialog(self.controller, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_ui()

    def _create_task(self, payload: dict) -> None:
        title = payload.get("title", "")
        description = payload.get("description", "")
        start_now = payload.get("start_now", False)
        task = self.controller.create_task(title, description, start_now=start_now)
        self.refresh_ui()
        if payload.get("on_portal"):
            self._create_portal_task_for(task.id, title, description, payload.get("company_id"))

    def _create_portal_task_for(self, task_id, title, description, company_id) -> None:
        webhook = self.controller.bitrix_webhook()
        if not looks_like_webhook(webhook):
            QMessageBox.warning(
                self, "Битрикс24",
                "Укажите URL вебхука в настройках, чтобы создавать задачи на портале.",
            )
            return

        def work():
            client = bitrix_client(self.controller, webhook)
            return client.create_portal_task(
                title, description, client.current_user_id(), company_id
            )

        self._create_thread = _CallableThread(work, self)
        self._create_thread.succeeded.connect(
            lambda portal_id: self._on_portal_task_created(task_id, portal_id)
        )
        self._create_thread.failed.connect(
            lambda message: QMessageBox.warning(
                self, "Битрикс24", f"Не удалось создать задачу на портале: {message}"
            )
        )
        self._create_thread.start()

    def _on_portal_task_created(self, task_id, portal_id) -> None:
        self.controller.link_bitrix(task_id, {"source": "task", "id": str(portal_id)})
        self.refresh_ui()

    def _set_view(self, view: str) -> None:
        self._current_view = view
        self._pinned_task_row_id = None
        self.refresh_ui()

    def _set_date(self, qdate: QDate) -> None:
        self._selected_date = qdate.toString("yyyy-MM-dd")
        self._current_view = "date"
        self._pinned_task_row_id = None
        self.refresh_ui()

    def _toggle_plan(self, task_id: str) -> None:
        task = self.controller.find_task(task_id)
        if self.controller.in_today_plan(task):
            self.controller.remove_from_plan(task_id)
        else:
            self.controller.add_to_plan(task_id)
        self.refresh_ui()

    def _start_focus_timer(self, minutes: int) -> None:
        self.controller.start_focus_timer(minutes)
        self.refresh_ui()
        self._floating_user_dismissed = False
        self.floating.show_at_default_corner()
        self._update_floating()
        self._show_tray_message(
            "Режим концентрации",
            f"Запущен таймер на {minutes} мин.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _stop_focus_timer(self) -> None:
        paused_id = self.controller.focus_paused_task_id
        self.controller.stop_focus_timer()
        self.refresh_ui()
        if paused_id:
            self._prompt_focus_resume(paused_id)

    def _start_task(self, task_id: str) -> None:
        self.controller.start_task(task_id)
        self.refresh_ui()
        self._track_floating_task(task_id)
        self._update_tray_tooltip()
        task = self.controller.find_task(task_id)
        self._show_tray_message("Таймер запущен", task.title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _stop_task(self, task_id: str) -> None:
        task = self.controller.stop_task(task_id)
        self.refresh_ui()
        self._track_floating_task(task_id)
        self._update_tray_tooltip()
        self._show_tray_message("Таймер остановлен", task.title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _confirm_complete_task(self, task_id: str) -> None:
        task = self.controller.find_task(task_id)
        answer = QMessageBox.question(
            self,
            "Подтверждение",
            f"Задача завершена, закрываю?\n\n{task.title}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.complete_task(task_id)
            self.refresh_ui()
            self._mini_task_id = None
            self.floating.hide()
            self._update_tray_tooltip()
            self._sync_portal_completion(self.controller.find_task(task_id), complete=True)
            self._show_tray_message("Задача завершена", task.title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _resume_task(self, task_id: str) -> None:
        self.controller.resume_completed_task(task_id)
        self.refresh_ui()
        self._track_floating_task(task_id)
        self._update_tray_tooltip()
        task = self.controller.find_task(task_id)
        self._sync_portal_completion(task, complete=False)
        self._show_tray_message("Задача возобновлена", task.title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _sync_portal_completion(self, task: Task, complete: bool) -> None:
        """Queue a complete/renew of the linked Bitrix24 task.

        Operations are serialized (one at a time, in action order) so that, e.g.,
        complete→resume→complete always leaves the portal task in the last state.
        """
        link = task.bitrix if task else None
        if not (isinstance(link, dict) and link.get("source") == "task" and link.get("id")):
            return
        webhook = self.controller.bitrix_webhook()
        if not looks_like_webhook(webhook):
            return
        self._portal_sync_queue.append((link["id"], complete, webhook))
        self._process_portal_sync_queue()

    def _process_portal_sync_queue(self) -> None:
        if self._portal_sync_busy or not self._portal_sync_queue:
            return
        portal_id, complete, webhook = self._portal_sync_queue.pop(0)
        self._portal_sync_busy = True

        def work():
            client = bitrix_client(self.controller, webhook)
            if complete:
                client.complete_portal_task(portal_id)
            else:
                client.renew_portal_task(portal_id)

        self._portal_sync_thread = _CallableThread(work, self)
        self._portal_sync_thread.failed.connect(
            lambda message: QMessageBox.warning(
                self, "Битрикс24", f"Не удалось синхронизировать задачу на портале: {message}"
            )
        )
        self._portal_sync_thread.finished.connect(self._on_portal_sync_done)
        self._portal_sync_thread.start()

    def _on_portal_sync_done(self) -> None:
        self._portal_sync_busy = False
        self._process_portal_sync_queue()

    def _open_history(self, task_id: str) -> None:
        task = self.controller.find_task(task_id)
        dialog = SessionEditDialog(self.controller, task, self)
        dialog.exec()
        self.refresh_ui()

    def _open_task_edit(self, task_id: str) -> None:
        task = self.controller.find_task(task_id)
        dialog = TaskEditDialog(self.controller, task, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_ui()

    def _on_task_row_selected(self, task_id: str) -> None:
        self._pinned_task_row_id = task_id
        for tid, row in self._task_rows.items():
            row.set_pinned(tid == task_id)

    def _on_task_row_deselected(self, task_id: str) -> None:
        if self._pinned_task_row_id == task_id:
            self._pinned_task_row_id = None

    def _confirm_delete_task(self, task_id: str) -> None:
        task = self.controller.find_task(task_id)
        answer = QMessageBox.question(
            self,
            "Удаление задачи",
            f"Действительно удалить задачу?\n\n{task.title}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.delete_task(task_id)
            if self._pinned_task_row_id == task_id:
                self._pinned_task_row_id = None
            if self._mini_task_id == task_id:
                self._mini_task_id = None
                self.floating.hide()
            self.refresh_ui()

    def _stop_active(self) -> None:
        panel_task = self.controller.timer_panel_task()
        if not panel_task:
            return
        if panel_task.status == TaskStatus.RUNNING:
            self._stop_task(panel_task.id)
        elif panel_task.status == TaskStatus.PAUSED:
            self._start_task(panel_task.id)

    def _complete_active(self) -> None:
        panel_task = self.controller.timer_panel_task()
        if panel_task:
            self._confirm_complete_task(panel_task.id)

    def _tick(self) -> None:
        status, task = self.controller.check_reminders()
        self._refresh_active_panel()
        self._update_task_row_times()
        focus_status, focus_payload = self.controller.check_focus_timer()
        self._refresh_focus_panel()
        if status == "needs_confirmation" and task:
            self._show_continue_prompt(task)
        elif status == "auto_stopped" and task:
            self.refresh_ui()
            grace_minutes = int(self.controller.reminder_grace.total_seconds() // 60)
            self._show_tray_message(
                "Таймер поставлен на стоп",
                f"{task.title}: подтверждение не было получено в течение {grace_minutes} мин.",
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )
        self._update_floating()
        self._update_tray_tooltip()
        if focus_status == "finished":
            paused_task_id = self.controller.focus_paused_task_id
            QApplication.beep()
            QApplication.beep()
            QApplication.beep()
            duration_label = f"{focus_payload} мин." if focus_payload else "выбранное время"
            self._show_tray_message(
                "Фокус-сессия завершена",
                f"Таймер концентрации на {duration_label} закончился.",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
            if paused_task_id:
                self._prompt_focus_resume(paused_task_id)
            else:
                self.controller.take_focus_paused_task_id()
                self.refresh_ui()
                QMessageBox.information(
                    self,
                    "Фокус-сессия завершена",
                    "Время концентрации вышло.",
                )
            return

    def _show_continue_prompt(self, task: Task) -> None:
        minutes = self.controller.reminder_interval_minutes()
        grace_minutes = int(self.controller.reminder_grace.total_seconds() // 60)
        self._show_tray_message(
            "Подтвердите продолжение",
            f"{task.title} выполняется уже {minutes} мин. "
            f"Без подтверждения через {grace_minutes} мин таймер остановится.",
            QSystemTrayIcon.MessageIcon.Information,
            6000,
        )
        answer = QMessageBox.question(
            self,
            "Подтверждение продолжения",
            f"Задача выполняется уже {minutes} мин.\n\n{task.title}\n\nПродолжаете работу?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.confirm_continue(task.id)
        else:
            self.controller.stop_task(task.id)
        self.refresh_ui()

    def _show_tray_message(
        self,
        title: str,
        text: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        timeout: int = 4000,
    ) -> None:
        if self.tray_available and self.tray.isVisible():
            self.tray.showMessage(title, text, icon, timeout)

    def _update_tray_tooltip(
        self,
        floating_task: Task | None | object = _TRAY_TOOLTIP_FLOATING_AUTO,
    ) -> None:
        if not self.tray_available:
            return
        window_open = main_window_is_open(
            is_visible=self.isVisible(),
            is_minimized=self.isMinimized(),
        )
        running_titles = [task.title for task in self.controller.running_tasks()]
        display_task: Task | None = None
        focus_line: str | None = None
        if not window_open:
            if floating_task is _TRAY_TOOLTIP_FLOATING_AUTO:
                display_task, tracked_id = self._floating_task_state()
                self._mini_task_id = tracked_id
            else:
                display_task = floating_task  # type: ignore[assignment]
            view = resolve_floating_view(
                focus_remaining_seconds=self.controller.focus_remaining_seconds(),
                focus_session_task_id=self.controller.focus_session_task_id,
                find_task=self.controller.find_task,
                floating_task=display_task,
            )
            if view is not None and view.is_focus:
                focus_line = f"{view.title} · {view.time_text}"
        task_titles = tray_tooltip_task_titles(
            running_task_titles=running_titles,
            floating_task=display_task if focus_line is None else None,
            focus_line=focus_line,
        )
        self.tray.setToolTip(
            format_tray_tooltip(
                window_visible=window_open,
                app_title=resolve_app_title(),
                task_titles=task_titles,
            )
        )

    def _floating_task_state(self) -> tuple[Task | None, str | None]:
        return resolve_floating_task(
            active=self.controller.active_task(),
            tracked_task_id=self._mini_task_id,
            find_task=self.controller.find_task,
            panel_task=self.controller.timer_panel_task(),
        )

    def _resolve_floating_task(self) -> Task | None:
        task, tracked_id = self._floating_task_state()
        self._mini_task_id = tracked_id
        return task

    def _hide_to_tray(self) -> None:
        if not self.tray_available or not self.tray.isVisible():
            return
        if self._tray_collapsed and not self.isVisible():
            return
        self._tray_collapsed = True
        self.hide()
        task: Task | None
        if self._floating_user_dismissed:
            task = self._resolve_floating_task()
        else:
            task = self._show_floating()
        self._update_tray_tooltip(floating_task=task)
        if task is not None and task.status == TaskStatus.RUNNING and task.active_session() is not None:
            elapsed = format_duration(task.total_seconds(datetime.now()))
            self._show_tray_message(
                task.title,
                f"Таймер: {elapsed}. Приложение свернуто в трей.",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    def _track_floating_task(self, task_id: str) -> None:
        """Remember which task the tray mini-widget should display."""
        self._mini_task_id = task_id

    def _show_floating_from_tray(self) -> None:
        self._floating_user_dismissed = False
        self._show_floating(force=True)

    def _resolve_floating_view(self) -> FloatingView | None:
        task = self._resolve_floating_task()
        return resolve_floating_view(
            focus_remaining_seconds=self.controller.focus_remaining_seconds(),
            focus_session_task_id=self.controller.focus_session_task_id,
            find_task=self.controller.find_task,
            floating_task=task,
        )

    def _show_floating(self, *, force: bool = False) -> Task | None:
        if self._floating_user_dismissed and not force:
            return self._resolve_floating_task()
        self._floating_user_dismissed = False
        view = self._resolve_floating_view()
        if view is None:
            self.floating.hide()
            return None
        self.floating.show_at_default_corner()
        self._update_floating()
        return self._resolve_floating_task()

    def _floating_close(self) -> None:
        self._floating_user_dismissed = True
        self.floating.hide()
        self._update_tray_tooltip()
        self._show_tray_message(
            "Виджет скрыт",
            "Таймер продолжает работать. Откройте приложение или «Показать виджет» из трея.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _update_floating(self) -> None:
        if not self.floating.isVisible():
            return
        view = self._resolve_floating_view()
        if view is None:
            self.floating.hide()
            return
        self.floating.update_view(
            view.title,
            view.time_text,
            running=view.running,
            is_focus=view.is_focus,
        )

    def _floating_stop(self) -> None:
        view = self._resolve_floating_view()
        if view is None:
            return
        if view.is_focus:
            self.controller.stop_focus_timer()
            self.refresh_ui()
            self._update_floating()
            return
        task = self._resolve_floating_task()
        if task is None:
            return
        self.controller.stop_task(task.id)
        self.refresh_ui()
        self._update_floating()

    def _floating_start(self) -> None:
        view = self._resolve_floating_view()
        if view is None or view.is_focus:
            return
        task = self._resolve_floating_task()
        if task is None:
            return
        self.controller.start_task(task.id)
        self.refresh_ui()
        self._update_floating()

    def _request_exit(self) -> None:
        if not self._confirm_exit():
            return
        self._exit_application()

    def _confirm_exit(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Закрытие приложения",
            "Завершить работу с приложением?\n\n"
            "Да: остановить текущую задачу и закрыть приложение.\n"
            "Нет: оставить приложение запущенным.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _exit_application(self) -> None:
        active = self.controller.active_task()
        if active:
            self.controller.stop_task(active.id)
        self.floating.hide()
        if self.tray_available:
            self.tray.hide()
        self.app.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray_available and self.tray.isVisible():
            answer = QMessageBox.question(
                self,
                "Закрытие приложения",
                "Завершить работу с приложением?\n\n"
                "Да: остановить текущую задачу и закрыть приложение.\n"
                "Нет: свернуть в трей.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                event.accept()
                self._exit_application()
                return
            self._hide_to_tray()
            event.ignore()
            return
        super().closeEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self._hide_to_tray)

    def bring_to_front(self) -> None:
        """Показать главное окно (повторный запуск, трей)."""
        self._restore_from_tray()

    def _toggle_main_window_from_tray(self) -> None:
        if main_window_is_open(is_visible=self.isVisible(), is_minimized=self.isMinimized()):
            self._hide_to_tray()
        else:
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self._tray_collapsed = False
        self.floating.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._update_tray_tooltip()

    def _handle_tray_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason not in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            return
        now = time.monotonic()
        if tray_activation_is_debounced(now=now, last_at=self._last_tray_activation_at):
            return
        self._last_tray_activation_at = now
        self._toggle_main_window_from_tray()
