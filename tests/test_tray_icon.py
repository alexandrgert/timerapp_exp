from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

from timerapp_ag.ui import tray_icon
from timerapp_ag.ui.tray_icon import (
    build_tray_app_icon,
    clear_tray_app_icon_cache,
    paint_dev_label,
)


@pytest.fixture(autouse=True)
def reset_tray_icon_cache() -> None:
    clear_tray_app_icon_cache()
    yield
    clear_tray_app_icon_cache()


def _count_bright_pixels(pixmap: QPixmap, *, threshold: int = 200) -> int:
    image = pixmap.toImage()
    bright = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.red() >= threshold and color.green() >= threshold and color.blue() >= threshold:
                bright += 1
    return bright


def test_fit_dev_font_size_grows_with_icon_size(qapp) -> None:
    small = tray_icon._fit_dev_font_size(QFont(), "dev", 22)
    large = tray_icon._fit_dev_font_size(QFont(), "dev", 128)
    assert large > small
    assert tray_icon._fit_dev_font_size(QFont(), "dev", 16) >= 4


def test_paint_dev_label_adds_white_pixels(qapp) -> None:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor("#204080"))
    before = _count_bright_pixels(pixmap)

    painter = QPainter(pixmap)
    paint_dev_label(painter, 32)
    painter.end()

    assert _count_bright_pixels(pixmap) > before + 20


def _count_different_pixels(left: QPixmap, right: QPixmap) -> int:
    left_image = left.toImage()
    right_image = right.toImage()
    width = min(left_image.width(), right_image.width())
    height = min(left_image.height(), right_image.height())
    different = 0
    for y in range(height):
        for x in range(width):
            if left_image.pixelColor(x, y) != right_image.pixelColor(x, y):
                different += 1
    return different


def test_build_tray_app_icon_dev_overlay(qapp) -> None:
    style = QApplication.style()
    assert style is not None

    size = 22
    base = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon).pixmap(size, size)
    icon = build_tray_app_icon(style)
    painted = icon.pixmap(size, size)

    assert not painted.isNull()
    assert painted.size() == base.size()
    assert _count_different_pixels(base, painted) > 40


def test_build_tray_app_icon_is_cached(qapp) -> None:
    first = build_tray_app_icon()
    second = build_tray_app_icon()
    assert first is second
    assert not first.isNull()


def test_build_tray_app_icon_requires_style(qapp, monkeypatch) -> None:
    monkeypatch.setattr(tray_icon.QApplication, "style", staticmethod(lambda: None))
    with pytest.raises(RuntimeError, match="unavailable"):
        build_tray_app_icon()


def test_clear_tray_app_icon_cache_forces_rebuild(qapp) -> None:
    style = QApplication.style()
    assert style is not None
    first = build_tray_app_icon(style)
    clear_tray_app_icon_cache()
    second = build_tray_app_icon(style)
    assert first is not second
    assert not second.isNull()
