from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FloatingTimer(QWidget):
    """Small always-on-top widget shown in the tray for the current or last task."""

    stop_requested = Signal()
    start_requested = Signal()
    restore_requested = Signal()
    close_requested = Signal()

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
        layout.setContentsMargins(14, 8, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addStretch(1)

        self.dev_badge = QLabel("DEV")
        self.dev_badge.setObjectName("floatingDevBadge")
        top.addWidget(self.dev_badge, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("floatingClose")
        self.close_button.setFixedSize(20, 20)
        self.close_button.setToolTip("Скрыть виджет (таймер продолжит работать)")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.close_requested.emit)
        top.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(top)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.name_label = QLabel("Задача")
        self.name_label.setObjectName("floatingName")
        header.addWidget(self.name_label, 1)

        layout.addLayout(header)

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
            QLabel#floatingDevBadge {
                background: transparent;
                color: #ffffff;
                font-size: 17px;
                font-weight: 900;
                letter-spacing: 1.5px;
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
            QLabel#floatingTime[focus="true"] {
                color: #7DD3FC;
            }
            QLabel#floatingName[focus="true"] {
                color: rgba(125, 211, 252, 0.92);
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
            QPushButton#floatingClose {
                background: transparent;
                color: rgba(255, 255, 255, 0.55);
                border: none;
                font-size: 12px;
                font-weight: 700;
                padding: 0;
            }
            QPushButton#floatingClose:hover {
                color: #ffffff;
                background: rgba(255, 255, 255, 0.12);
                border-radius: 4px;
            }
            QPushButton#floatingStart:disabled, QPushButton#floatingStop:disabled {
                color: rgba(255, 255, 255, 0.32);
                background: rgba(255, 255, 255, 0.05);
            }
            """
        )

    def update_view(
        self,
        title: str,
        time_text: str,
        *,
        running: bool,
        is_focus: bool = False,
    ) -> None:
        elided = self.name_label.fontMetrics().elidedText(
            title,
            Qt.TextElideMode.ElideRight,
            max(80, self.name_label.width() or self.width() - 28),
        )
        self.name_label.setText(elided)
        self.time_label.setText(time_text)
        self.name_label.setProperty("focus", is_focus)
        self.time_label.setProperty("focus", is_focus)
        for widget in (self.name_label, self.time_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.stop_button.setEnabled(running)
        self.start_button.setEnabled(not running and not is_focus)
        self.stop_button.setToolTip(
            "Остановить фокус" if is_focus else "Стоп"
        )
        self.start_button.setToolTip("Старт")

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
