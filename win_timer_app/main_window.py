from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, QEvent, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .bitrix import Bitrix24Client, looks_like_webhook
from .controller import AppController, format_day_label, format_duration
from .models import Task, TaskStatus


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
    create_requested = Signal(str, str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Новая задача")
        self.setModal(True)
        self.resize(460, 300)

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
        self.description_edit.setFixedHeight(100)
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

    def open_clean(self) -> None:
        self.title_edit.clear()
        self.description_edit.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.title_edit.setFocus()

    def _emit_request(self, start_now: bool) -> None:
        title = self.title_edit.text().strip()
        description = self.description_edit.toPlainText().strip()
        if not title:
            self.title_edit.setFocus()
            return
        self.create_requested.emit(title, description, start_now)
        self.accept()


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


class SettingsDialog(QDialog):
    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Настройки")
        self.resize(520, 300)
        self._test_thread: _CallableThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        hint = QLabel(
            "Через указанное время после старта таймера или после ответа «Продолжить» "
            "приложение снова спросит, продолжать ли работу над задачей."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.reminder_spin = QSpinBox()
        self.reminder_spin.setRange(1, 24 * 60)
        self.reminder_spin.setSuffix(" мин")
        self.reminder_spin.setValue(controller.reminder_interval_minutes())
        form.addRow("Интервал напоминания", self.reminder_spin)

        self.webhook_edit = QLineEdit()
        self.webhook_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.webhook_edit.setPlaceholderText("https://портал.bitrix24.ru/rest/1/токен/")
        self.webhook_edit.setText(controller.bitrix_webhook())
        form.addRow("URL вебхука Битрикс24", self.webhook_edit)
        layout.addLayout(form)

        webhook_controls = QHBoxLayout()
        self.show_webhook_checkbox = QCheckBox("Показать")
        self.show_webhook_checkbox.toggled.connect(self._toggle_webhook_echo)
        webhook_controls.addWidget(self.show_webhook_checkbox)
        webhook_controls.addStretch(1)
        self.test_button = QPushButton("Проверить соединение")
        self.test_button.clicked.connect(self._test_connection)
        webhook_controls.addWidget(self.test_button)
        layout.addLayout(webhook_controls)

        self.webhook_status = QLabel("")
        self.webhook_status.setWordWrap(True)
        layout.addWidget(self.webhook_status)

        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
            lambda: Bitrix24Client(url).test_connection(), self
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

    def _set_status(self, text: str, ok: bool | None) -> None:
        color = {True: "#2d6b40", False: "#9b3c3c", None: "#5f6b7c"}[ok]
        self.webhook_status.setText(text)
        self.webhook_status.setStyleSheet(f"color: {color}; background: transparent;")

    def _await_test_thread(self) -> None:
        thread = self._test_thread
        if thread is not None and thread.isRunning():
            thread.wait(5000)

    def accept(self) -> None:
        self._await_test_thread()
        super().accept()

    def reject(self) -> None:
        self._await_test_thread()
        super().reject()


class SessionEditDialog(QDialog):
    def __init__(self, controller: AppController, task: Task, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.task = task
        self.selected_session_id: str | None = None
        self.setWindowTitle(f"История: {task.title}")
        self.resize(620, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._load_current_session)
        layout.addWidget(self.list_widget)

        form = QFormLayout()
        self.start_edit = QDateTimeEdit()
        self.start_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self.start_edit.setCalendarPopup(True)
        form.addRow("Начало", self.start_edit)

        self.end_edit = QDateTimeEdit()
        self.end_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self.end_edit.setCalendarPopup(True)
        form.addRow("Окончание", self.end_edit)
        layout.addLayout(form)

        actions = QHBoxLayout()
        add_button = QPushButton("Добавить запись")
        add_button.setObjectName("ghostButton")
        add_button.clicked.connect(self._add_session)
        actions.addWidget(add_button)
        self.delete_session_button = QPushButton("Удалить запись")
        self.delete_session_button.setObjectName("deleteGhostButton")
        self.delete_session_button.clicked.connect(self._delete_current_session)
        actions.addWidget(self.delete_session_button)
        actions.addStretch()
        save_button = QPushButton("Сохранить интервал")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save_current_session)
        actions.addWidget(save_button)
        layout.addLayout(actions)

        self._reload()

    def _reload(self) -> None:
        self.list_widget.clear()
        for session in self.task.sessions:
            start = datetime.fromisoformat(session.started_at)
            end = datetime.fromisoformat(session.ended_at) if session.ended_at else None
            duration = session.duration_seconds(datetime.now())
            title = f"{start.strftime('%d.%m %H:%M:%S')} -> {end.strftime('%d.%m %H:%M:%S') if end else 'идет'}  ({format_duration(duration)})"
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, session.id)
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        else:
            self.selected_session_id = None
            end_q = QDateTime.currentDateTime()
            self.end_edit.setDateTime(end_q)
            self.start_edit.setDateTime(end_q.addSecs(-3600))
        self.delete_session_button.setEnabled(self.list_widget.count() > 0)

    def _add_session(self) -> None:
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        try:
            session = self.controller.add_session(self.task.id, start, end)
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        self.task = self.controller.find_task(self.task.id)
        self._reload()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == session.id:
                self.list_widget.setCurrentRow(row)
                break

    def _delete_current_session(self) -> None:
        if not self.selected_session_id:
            return
        answer = QMessageBox.question(
            self,
            "Удаление",
            "Удалить выбранную запись из истории?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controller.delete_session(self.task.id, self.selected_session_id)
        except KeyError:
            return
        self.task = self.controller.find_task(self.task.id)
        self._reload()

    def _load_current_session(self, item: QListWidgetItem | None) -> None:
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        session = next((entry for entry in self.task.sessions if entry.id == session_id), None)
        if session is None:
            return
        self.selected_session_id = session.id
        self.start_edit.setDateTime(QDateTime.fromString(session.started_at, Qt.DateFormat.ISODate))
        end_value = session.ended_at or datetime.now().isoformat()
        self.end_edit.setDateTime(QDateTime.fromString(end_value, Qt.DateFormat.ISODate))

    def _save_current_session(self) -> None:
        if not self.selected_session_id:
            return
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        try:
            self.controller.update_session(self.task.id, self.selected_session_id, start, end)
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        self.task = self.controller.find_task(self.task.id)
        self._reload()
        QMessageBox.information(self, "Сохранено", "Интервал обновлен.")


class TaskRow(QFrame):
    start_requested = Signal(str)
    stop_requested = Signal(str)
    complete_requested = Signal(str)
    resume_requested = Signal(str)
    history_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, controller: AppController, task: Task) -> None:
        super().__init__()
        self.setObjectName("taskRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        title_label = QLabel(task.title)
        if task.status == TaskStatus.COMPLETED:
            font = title_label.font()
            font.setStrikeOut(True)
            title_label.setFont(font)
        title_block.addWidget(title_label)

        if task.description:
            description_label = QLabel(task.description)
            description_label.setObjectName("descriptionLabel")
            description_label.setWordWrap(True)
            title_block.addWidget(description_label)

        top.addLayout(title_block, 1)

        time_label = QLabel(f"Затрачено: {controller.task_elapsed_text(task)}")
        time_label.setObjectName("timeLabel")
        top.addWidget(time_label)

        history_button = QPushButton("История")
        history_button.setObjectName("ghostButton")
        history_button.clicked.connect(lambda: self.history_requested.emit(task.id))
        top.addWidget(history_button)

        delete_button = QPushButton()
        delete_button.setObjectName("deleteGhostButton")
        delete_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        delete_button.setToolTip("Удалить задачу")
        delete_button.clicked.connect(lambda: self.delete_requested.emit(task.id))
        top.addWidget(delete_button)
        layout.addLayout(top)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        if task.status == TaskStatus.COMPLETED:
            resume_button = QPushButton("Возобновить")
            resume_button.setObjectName("resumeButton")
            resume_button.clicked.connect(lambda: self.resume_requested.emit(task.id))
            controls.addWidget(resume_button)
        else:
            start_text = "Стоп" if task.status == TaskStatus.RUNNING else "Старт"
            start_button = QPushButton(start_text)
            start_button.setObjectName("stopButton" if task.status == TaskStatus.RUNNING else "startButton")
            if task.status == TaskStatus.RUNNING:
                start_button.clicked.connect(lambda: self.stop_requested.emit(task.id))
            else:
                start_button.clicked.connect(lambda: self.start_requested.emit(task.id))
            controls.addWidget(start_button)

            complete_button = QPushButton("Завершить")
            complete_button.setObjectName("completeButton")
            complete_button.clicked.connect(lambda: self.complete_requested.emit(task.id))
            controls.addWidget(complete_button)

        controls.addStretch(1)
        layout.addLayout(controls)


class DaySection(QFrame):
    start_requested = Signal(str)
    stop_requested = Signal(str)
    complete_requested = Signal(str)
    resume_requested = Signal(str)
    history_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, controller: AppController, day: str, tasks: list[Task]) -> None:
        super().__init__()
        self.setObjectName("dayCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel(format_day_label(day))
        title.setObjectName("sectionTitle")
        header.addWidget(title)

        total = QLabel(f"Всего затрачено: {format_duration(controller.day_total_seconds(day))}")
        total.setObjectName("summaryLabel")
        header.addWidget(total)
        header.addStretch(1)
        layout.addLayout(header)

        for task in tasks:
            row = TaskRow(controller, task)
            row.start_requested.connect(self.start_requested.emit)
            row.stop_requested.connect(self.stop_requested.emit)
            row.complete_requested.connect(self.complete_requested.emit)
            row.resume_requested.connect(self.resume_requested.emit)
            row.history_requested.connect(self.history_requested.emit)
            row.delete_requested.connect(self.delete_requested.emit)
            layout.addWidget(row)


class FloatingTimer(QWidget):
    """Small always-on-top translucent widget shown while a task runs in the tray."""

    stop_requested = Signal()
    start_requested = Signal()
    restore_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.9)
        self._drag_offset = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("floatingCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)

        self.name_label = QLabel("Задача")
        self.name_label.setObjectName("floatingName")
        layout.addWidget(self.name_label)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self.time_label = QLabel("00:00:00")
        self.time_label.setObjectName("floatingTime")
        bottom.addWidget(self.time_label)
        bottom.addStretch(1)

        self.start_button = QPushButton("▶")
        self.start_button.setObjectName("floatingStart")
        self.start_button.setFixedSize(30, 26)
        self.start_button.setToolTip("Старт")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.clicked.connect(self.start_requested.emit)
        bottom.addWidget(self.start_button)

        self.stop_button = QPushButton("⏸")
        self.stop_button.setObjectName("floatingStop")
        self.stop_button.setFixedSize(30, 26)
        self.stop_button.setToolTip("Стоп")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        bottom.addWidget(self.stop_button)

        layout.addLayout(bottom)

        self.setFixedWidth(232)
        self.setStyleSheet(
            """
            QFrame#floatingCard {
                background: rgba(18, 20, 25, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 16px;
            }
            QLabel#floatingName {
                background: transparent;
                color: rgba(255, 255, 255, 0.82);
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#floatingTime {
                background: transparent;
                color: #ffffff;
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QPushButton#floatingStart, QPushButton#floatingStop {
                background: rgba(255, 255, 255, 0.12);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
                padding: 0;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#floatingStart:hover, QPushButton#floatingStop:hover {
                background: rgba(255, 255, 255, 0.24);
            }
            QPushButton#floatingStart:disabled, QPushButton#floatingStop:disabled {
                color: rgba(255, 255, 255, 0.32);
                background: rgba(255, 255, 255, 0.05);
            }
            """
        )

    def update_view(self, title: str, elapsed: str, running: bool) -> None:
        elided = self.name_label.fontMetrics().elidedText(
            title, Qt.TextElideMode.ElideRight, 196
        )
        self.name_label.setText(elided)
        self.time_label.setText(elapsed)
        self.stop_button.setEnabled(running)
        self.start_button.setEnabled(not running)

    def show_at_default_corner(self) -> None:
        if not self.isVisible():
            self.adjustSize()
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                x = geo.right() - self.width() - 24
                y = geo.bottom() - self.height() - 24
                self.move(max(geo.left(), x), max(geo.top(), y))
        self.show()
        self.raise_()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event) -> None:
        self.restore_requested.emit()


class MainWindow(QMainWindow):
    focus_presets = (5, 10, 20, 30, 40)

    def __init__(self, controller: AppController, app: QApplication) -> None:
        super().__init__()
        self.controller = controller
        self.app = app
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.app_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(self.app_icon)
        self.setWindowTitle("Task Timer")
        self.resize(980, 680)
        self.setMinimumSize(800, 600)
        self.create_dialog = CreateTaskDialog(self)
        self.create_dialog.create_requested.connect(self._create_task)
        self._mini_task_id: str | None = None
        self.floating = FloatingTimer()
        self.floating.stop_requested.connect(self._floating_stop)
        self.floating.start_requested.connect(self._floating_start)
        self.floating.restore_requested.connect(self._restore_from_tray)
        self._build_ui()
        self._build_menu_bar()
        self._build_tray()
        self._apply_styles()
        self.refresh_ui()

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start()

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._build_tasks_tab(), "Задачи")
        self.tabs.addTab(self._build_focus_tab(), "Фокус")
        self.tabs.setCornerWidget(
            self._build_settings_button(), Qt.Corner.TopRightCorner
        )

    def _build_settings_button(self) -> QWidget:
        button = QPushButton("⚙")
        button.setObjectName("settingsButton")
        button.setToolTip("Настройки")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(34, 34)
        button.clicked.connect(self._open_settings)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 14, 0)
        layout.addWidget(button)
        return container

    def _build_tasks_tab(self) -> QWidget:
        root = QWidget()

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(18)

        left_column = QVBoxLayout()
        left_column.setSpacing(14)
        main_layout.addLayout(left_column, 3)

        top_actions = QHBoxLayout()
        top_actions.setSpacing(12)

        section_title = QLabel("Задачи по дням")
        section_title.setObjectName("sectionTitle")
        top_actions.addWidget(section_title)
        top_actions.addStretch(1)

        add_button = QPushButton("Новая задача")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self._open_create_dialog)
        top_actions.addWidget(add_button)
        left_column.addLayout(top_actions)

        filter_row = QHBoxLayout()
        self.open_only_checkbox = QCheckBox("Только незавершенные")
        self.open_only_checkbox.toggled.connect(self._toggle_open_only)
        filter_row.addWidget(self.open_only_checkbox)
        filter_row.addStretch(1)
        left_column.addLayout(filter_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.days_container = QWidget()
        self.days_layout = QVBoxLayout(self.days_container)
        self.days_layout.setContentsMargins(0, 0, 0, 0)
        self.days_layout.setSpacing(14)
        self.days_layout.addStretch(1)
        self.scroll_area.setWidget(self.days_container)
        left_column.addWidget(self.scroll_area, 1)

        self.timer_card = QFrame()
        self.timer_card.setObjectName("timerCard")
        self.timer_card.setMinimumWidth(300)
        self.timer_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        timer_layout = QVBoxLayout(self.timer_card)
        timer_layout.setContentsMargins(20, 20, 20, 20)
        timer_layout.setSpacing(12)

        current_title = QLabel("Текущая задача")
        current_title.setObjectName("timerHeading")
        timer_layout.addWidget(current_title)

        self.active_task_name = QLabel("Нет активной задачи")
        self.active_task_name.setWordWrap(True)
        self.active_task_name.setObjectName("activeTaskName")
        timer_layout.addWidget(self.active_task_name)

        time_stack = QVBoxLayout()
        time_stack.setSpacing(0)

        self.hours_display = QLabel("00")
        self.hours_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hours_display.setObjectName("hoursDisplay")
        time_stack.addWidget(self.hours_display)

        self.minutes_display = QLabel("00")
        self.minutes_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minutes_display.setObjectName("minutesDisplay")
        time_stack.addWidget(self.minutes_display)

        self.seconds_display = QLabel("00")
        self.seconds_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.seconds_display.setObjectName("secondsDisplay")
        time_stack.addWidget(self.seconds_display)

        timer_layout.addLayout(time_stack, 1)

        self.stop_active_button = QPushButton("Стоп")
        self.stop_active_button.clicked.connect(self._stop_active)
        timer_layout.addWidget(self.stop_active_button)

        self.complete_active_button = QPushButton("Завершить")
        self.complete_active_button.clicked.connect(self._complete_active)
        timer_layout.addWidget(self.complete_active_button)

        timer_layout.addStretch(1)
        main_layout.addWidget(self.timer_card, 1)
        return root

    def _build_focus_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 30, 40, 30)
        outer.setSpacing(0)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)

        focus_card = QFrame()
        focus_card.setObjectName("focusTabCard")
        focus_card.setMinimumWidth(380)
        focus_card.setMaximumWidth(560)
        focus_layout = QVBoxLayout(focus_card)
        focus_layout.setContentsMargins(28, 26, 28, 26)
        focus_layout.setSpacing(12)

        focus_title = QLabel("Режим концентрации")
        focus_title.setObjectName("focusHeading")
        focus_layout.addWidget(focus_title)

        focus_subtitle = QLabel("Обратный таймер для работы без отвлечений")
        focus_subtitle.setObjectName("focusSubheading")
        focus_subtitle.setWordWrap(True)
        focus_layout.addWidget(focus_subtitle)

        self.focus_display = QLabel("20:00")
        self.focus_display.setObjectName("focusDisplay")
        self.focus_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_layout.addWidget(self.focus_display)

        self.focus_status_label = QLabel("Готов к запуску")
        self.focus_status_label.setObjectName("focusStatusLabel")
        self.focus_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_layout.addWidget(self.focus_status_label)

        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(6)
        self.focus_buttons: dict[int, QPushButton] = {}
        for minutes in self.focus_presets:
            button = QPushButton(str(minutes))
            button.setObjectName("presetButton")
            button.clicked.connect(lambda _checked=False, value=minutes: self._start_focus_timer(value))
            self.focus_buttons[minutes] = button
            preset_layout.addWidget(button)
        focus_layout.addLayout(preset_layout)

        self.focus_stop_button = QPushButton("Остановить таймер")
        self.focus_stop_button.clicked.connect(self._stop_focus_timer)
        focus_layout.addWidget(self.focus_stop_button)

        row.addWidget(focus_card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        return page

    def _build_menu_bar(self) -> None:
        settings_action = QAction("Параметры…", self)
        settings_action.triggered.connect(self._open_settings)
        menu = self.menuBar().addMenu("Настройки")
        menu.addAction(settings_action)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app_icon, self)
        if not self.tray_available:
            return
        tray_menu = QMenu()

        show_action = QAction("Открыть", self)
        show_action.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(show_action)

        settings_action = QAction("Настройки…", self)
        settings_action.triggered.connect(self._open_settings)
        tray_menu.addAction(settings_action)

        tray_menu.addSeparator()

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self._exit_application)
        tray_menu.addAction(exit_action)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._handle_tray_activation)
        self.tray.show()

    def _apply_styles(self) -> None:
        self.app.setFont(QFont("Segoe UI", 10))

        self.setStyleSheet(
            """
            QWidget {
                background: #f3f4f6;
                color: #14161b;
            }
            QLabel {
                background: transparent;
            }
            QMainWindow {
                background: #eef1f4;
            }
            QFrame#createCard, QFrame#dayCard {
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(20, 22, 27, 0.08);
                border-radius: 26px;
            }
            QFrame#taskRow {
                background: #f9fafb;
                border: 1px solid rgba(20, 22, 27, 0.06);
                border-radius: 18px;
                padding: 14px;
            }
            QFrame#timerCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #121419, stop:0.45 #1c1f27, stop:1 #30333d);
                border-radius: 34px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QFrame#timerCard[active="true"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0f1613, stop:0.45 #163125, stop:1 #254439);
                border: 1px solid rgba(139, 214, 167, 0.22);
            }
            QTabWidget#mainTabs::pane {
                border: none;
                top: -1px;
            }
            QTabBar::tab {
                background: transparent;
                color: #5f6b7c;
                padding: 8px 20px;
                margin-right: 6px;
                border-radius: 12px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #151923;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: rgba(21, 25, 35, 0.06);
            }
            QFrame#focusTabCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #121419, stop:0.45 #1c1f27, stop:1 #30333d);
                border-radius: 28px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid rgba(20, 22, 27, 0.12);
                border-radius: 12px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #f5f7fb;
            }
            QPushButton#primaryButton {
                background: #151923;
                color: white;
                border: none;
            }
            QPushButton#startButton {
                background: #e6f6ea;
                border: 1px solid #c5e8cf;
                color: #2d6b40;
            }
            QPushButton#startButton:hover {
                background: #ddf1e3;
            }
            QPushButton#stopButton {
                background: #fde8e8;
                border: 1px solid #f4c5c5;
                color: #9b3c3c;
            }
            QPushButton#stopButton:hover {
                background: #fbdede;
            }
            QPushButton#resumeButton {
                background: #e8f0fd;
                border: 1px solid #c7d9f8;
                color: #3f6499;
            }
            QPushButton#resumeButton:hover {
                background: #dfe9fb;
            }
            QPushButton#completeButton:hover {
                background: #f5f7fb;
            }
            QPushButton#ghostButton {
                background: transparent;
                color: #5f6b7c;
                border: none;
                padding: 4px 8px;
            }
            QPushButton#ghostButton:hover {
                background: rgba(21, 25, 35, 0.05);
            }
            QPushButton#deleteGhostButton {
                background: transparent;
                border: none;
                padding: 4px 6px;
                color: #454b57;
            }
            QPushButton#deleteGhostButton:hover {
                background: rgba(21, 25, 35, 0.05);
            }
            QPushButton#settingsButton {
                background: transparent;
                border: none;
                border-radius: 17px;
                padding: 0;
                font-size: 18px;
                color: #5f6b7c;
            }
            QPushButton#settingsButton:hover {
                background: rgba(21, 25, 35, 0.08);
                color: #14161b;
            }
            QPushButton#presetButton {
                min-width: 0;
                padding: 10px 0;
                background: rgba(255, 255, 255, 0.08);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.14);
            }
            QPushButton#presetButton[active="true"] {
                background: #f3c96b;
                color: #19130a;
                border: none;
            }
            QLineEdit, QPlainTextEdit, QListWidget, QDateTimeEdit {
                background: white;
                border: 1px solid rgba(20, 22, 27, 0.12);
                border-radius: 12px;
                padding: 10px 12px;
            }
            QLabel#sectionTitle {
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#summaryLabel, QLabel#descriptionLabel, QLabel#timeLabel {
                color: #14161b;
            }
            QLabel#timerHeading {
                background: transparent;
                color: rgba(255, 255, 255, 0.78);
                font-size: 14px;
            }
            QLabel#activeTaskName {
                background: transparent;
                color: white;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#hoursDisplay {
                background: transparent;
                color: rgba(255, 255, 255, 0.72);
                font-size: 34px;
                font-weight: 700;
                line-height: 1.0;
            }
            QLabel#minutesDisplay {
                background: transparent;
                color: #ffffff;
                font-size: 76px;
                font-weight: 800;
                line-height: 0.92;
                letter-spacing: 1px;
            }
            QLabel#secondsDisplay {
                background: transparent;
                color: rgba(255, 255, 255, 0.72);
                font-size: 42px;
                font-weight: 700;
                line-height: 1.0;
            }
            QLabel#focusHeading {
                background: transparent;
                color: white;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#focusSubheading, QLabel#focusStatusLabel {
                background: transparent;
                color: rgba(255, 255, 255, 0.68);
                font-size: 12px;
            }
            QLabel#focusDisplay {
                background: transparent;
                color: #f8f7f2;
                font-size: 32px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            """
        )

    def refresh_ui(self) -> None:
        self.open_only_checkbox.blockSignals(True)
        self.open_only_checkbox.setChecked(self.controller.filter_open_only())
        self.open_only_checkbox.blockSignals(False)

        while self.days_layout.count():
            item = self.days_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for day, tasks in self.controller.tasks_by_day(open_only=self.controller.filter_open_only()):
            section = DaySection(self.controller, day, tasks)
            section.start_requested.connect(self._start_task)
            section.stop_requested.connect(self._stop_task)
            section.complete_requested.connect(self._confirm_complete_task)
            section.resume_requested.connect(self._resume_task)
            section.history_requested.connect(self._open_history)
            section.delete_requested.connect(self._confirm_delete_task)
            self.days_layout.addWidget(section)
        self.days_layout.addStretch(1)
        self._refresh_active_panel()
        self._refresh_focus_panel()

    def _refresh_active_panel(self) -> None:
        active = self.controller.active_task()
        if not active:
            self.timer_card.setProperty("active", False)
            self.style().unpolish(self.timer_card)
            self.style().polish(self.timer_card)
            self.timer_card.update()
            self.active_task_name.setText("Нет активной задачи")
            self.hours_display.setText("00")
            self.minutes_display.setText("00")
            self.seconds_display.setText("00")
            self.stop_active_button.setEnabled(False)
            self.complete_active_button.setEnabled(False)
            return
        self.active_task_name.setText(active.title)
        total = active.total_seconds(datetime.now())
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        self.timer_card.setProperty("active", True)
        self.style().unpolish(self.timer_card)
        self.style().polish(self.timer_card)
        self.timer_card.update()
        self.hours_display.setText(f"{hours:02d}")
        self.minutes_display.setText(f"{minutes:02d}")
        self.seconds_display.setText(f"{seconds:02d}")
        self.stop_active_button.setEnabled(True)
        self.complete_active_button.setEnabled(True)

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
        else:
            self.focus_display.setText(f"{selected_minutes:02d}:00")
            self.focus_status_label.setText("Готов к запуску")
            self.focus_stop_button.setEnabled(False)

        for minutes, button in self.focus_buttons.items():
            button.setProperty("active", minutes == selected_minutes)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.controller, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.set_reminder_interval_minutes(dialog.reminder_spin.value())
            self.controller.set_bitrix_webhook(dialog.webhook_edit.text())

    def _open_create_dialog(self) -> None:
        self.create_dialog.open_clean()

    def _create_task(self, title: str, description: str, start_now: bool) -> None:
        self.controller.create_task(title, description, start_now=start_now)
        self.refresh_ui()

    def _toggle_open_only(self, checked: bool) -> None:
        self.controller.set_filter_open_only(checked)
        self.refresh_ui()

    def _start_focus_timer(self, minutes: int) -> None:
        self.controller.start_focus_timer(minutes)
        self._refresh_focus_panel()
        self._show_tray_message(
            "Режим концентрации",
            f"Запущен таймер на {minutes} мин.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _stop_focus_timer(self) -> None:
        self.controller.stop_focus_timer()
        self._refresh_focus_panel()

    def _start_task(self, task_id: str) -> None:
        self.controller.start_task(task_id)
        self.refresh_ui()
        task = self.controller.find_task(task_id)
        self._show_tray_message("Таймер запущен", task.title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _stop_task(self, task_id: str) -> None:
        task = self.controller.stop_task(task_id)
        self.refresh_ui()
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
            self._show_tray_message("Задача завершена", task.title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _resume_task(self, task_id: str) -> None:
        self.controller.resume_completed_task(task_id)
        self.refresh_ui()
        task = self.controller.find_task(task_id)
        self._show_tray_message("Задача возобновлена", task.title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _open_history(self, task_id: str) -> None:
        task = self.controller.find_task(task_id)
        dialog = SessionEditDialog(self.controller, task, self)
        dialog.exec()
        self.refresh_ui()

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
            self.refresh_ui()

    def _stop_active(self) -> None:
        active = self.controller.active_task()
        if active:
            self._stop_task(active.id)

    def _complete_active(self) -> None:
        active = self.controller.active_task()
        if active:
            self._confirm_complete_task(active.id)

    def _tick(self) -> None:
        status, task = self.controller.check_reminders()
        self._refresh_active_panel()
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
        if focus_status == "finished":
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
            QMessageBox.information(
                self,
                "Фокус-сессия завершена",
                "Время концентрации вышло.",
            )

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

    def _hide_to_tray(self) -> None:
        if not self.tray_available or not self.tray.isVisible():
            return
        self.hide()
        self._show_floating()
        self._show_tray_message(
            "Приложение свернуто",
            "Таймер продолжает работать в системном трее.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _show_floating(self) -> None:
        active = self.controller.active_task()
        if active is not None:
            self._mini_task_id = active.id
        if self._mini_task_id is None:
            return
        try:
            self.controller.find_task(self._mini_task_id)
        except KeyError:
            self._mini_task_id = None
            return
        self.floating.show_at_default_corner()
        self._update_floating()

    def _update_floating(self) -> None:
        if not self.floating.isVisible():
            return
        if self._mini_task_id is None:
            self.floating.hide()
            return
        try:
            task = self.controller.find_task(self._mini_task_id)
        except KeyError:
            self._mini_task_id = None
            self.floating.hide()
            return
        running = task.status == TaskStatus.RUNNING and task.active_session() is not None
        elapsed = format_duration(task.total_seconds(datetime.now()))
        self.floating.update_view(task.title, elapsed, running)

    def _floating_stop(self) -> None:
        if self._mini_task_id is None:
            return
        self.controller.stop_task(self._mini_task_id)
        self.refresh_ui()
        self._update_floating()

    def _floating_start(self) -> None:
        if self._mini_task_id is None:
            return
        self.controller.start_task(self._mini_task_id)
        self.refresh_ui()
        self._update_floating()

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
                "Завершить работу с приложением?\n\nДа: остановить текущую задачу и закрыть приложение.\nНет: свернуть в трей.",
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

    def _restore_from_tray(self) -> None:
        self.floating.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _handle_tray_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._restore_from_tray()
