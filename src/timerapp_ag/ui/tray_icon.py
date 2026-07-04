"""Иконка приложения и трея: SP_ComputerIcon + белая надпись dev на экране."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import QApplication, QStyle

_TRAY_ICON: QIcon | None = None
_CACHED_STYLE_KEY: tuple[str, int] | None = None


def clear_tray_app_icon_cache() -> None:
    """Сброс кэша (смена темы Qt, тесты)."""
    global _TRAY_ICON, _CACHED_STYLE_KEY
    _TRAY_ICON = None
    _CACHED_STYLE_KEY = None


def _style_cache_key(style: QStyle) -> tuple[str, int]:
    return (style.metaObject().className(), id(style))


def _fit_dev_font_size(font: QFont, text: str, size: int) -> int:
    """Подобрать максимальный размер шрифта под всю высоту иконки."""
    margin = max(1, size // 20)
    max_w = size - 2 * margin
    max_h = size - 2 * margin
    for pixel in range(max_h, 3, -1):
        font.setPixelSize(pixel)
        metrics = QFontMetrics(font)
        if metrics.horizontalAdvance(text) <= max_w and metrics.height() <= max_h:
            return pixel
    return max(4, size // 5)


def paint_dev_label(painter: QPainter, size: int) -> None:
    """Строчные белые буквы dev на всю высоту иконки."""
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    text = "dev"
    text_rect = QRectF(0, 0, size, size)

    font = QFont()
    font.setBold(True)
    font.setPixelSize(_fit_dev_font_size(font, text, size))
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))

    painter.drawText(
        text_rect,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        "dev",
    )


def _build_icon_for_style(style: QStyle) -> QIcon:
    base = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    icon = QIcon()
    seen_physical: set[int] = set()
    for size in (16, 22, 24, 32, 48, 64, 128):
        pixmap = base.pixmap(size, size)
        if pixmap.isNull():
            continue
        physical = pixmap.width()
        if physical in seen_physical:
            continue
        seen_physical.add(physical)

        working = pixmap.copy()
        painter = QPainter(working)
        if not painter.isActive():
            continue
        paint_dev_label(painter, physical)
        painter.end()
        icon.addPixmap(working)

    return icon


def build_tray_app_icon(style: QStyle | None = None) -> QIcon:
    """QIcon: стандартный монитор Qt с надписью dev на экране."""
    global _TRAY_ICON, _CACHED_STYLE_KEY

    if style is None:
        app_style = QApplication.style()
        if app_style is None:
            raise RuntimeError("QApplication.style() is unavailable")
        style = app_style

    cache_key = _style_cache_key(style)
    if _TRAY_ICON is not None and _CACHED_STYLE_KEY == cache_key:
        return _TRAY_ICON

    icon = _build_icon_for_style(style)
    _TRAY_ICON = icon
    _CACHED_STYLE_KEY = cache_key
    return icon


def install_tray_icon_theme_refresh(refresh: Callable[[], None]) -> None:
    """Подписка на смену темы — refresh() пересобирает иконку трея/окна."""
    app = QApplication.instance()
    if app is None:
        return
    hints = app.styleHints()
    hints.colorSchemeChanged.connect(refresh)
    if hasattr(hints, "themeChanged"):
        hints.themeChanged.connect(refresh)
