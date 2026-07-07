from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QTextDocument, QTextOption
from PySide6.QtWidgets import QLabel, QPlainTextEdit

DESC_EDIT_MIN_HEIGHT = 72
DESC_EDIT_MAX_HEIGHT = 480
# Правая колонка 268 − отступы панели 36 − отступы карточки 28.
TIMER_DESC_TEXT_WIDTH = 204
TASK_ROW_DESC_HORIZONTAL_INSET = 43
TASK_ROW_DESC_BREAK_RUN = 40
TASK_ROW_NAME_MIN_WIDTH = 180
TASK_ROW_ACTIONS_OVERLAY_RESERVE = 40
TASK_ROW_PINNED_FOOTER_V_PAD = 8
TASK_ROW_PRIORITY_LEADING_WIDTH = 46


def break_long_unbroken_runs(text: str, *, max_run: int = TASK_ROW_DESC_BREAK_RUN) -> str:
    """Insert zero-width spaces so QLabel can wrap strings without spaces."""
    zero_width_space = "\u200b"

    def split_run(match: re.Match[str]) -> str:
        chunk = match.group(0)
        if len(chunk) <= max_run:
            return chunk
        return zero_width_space.join(
            chunk[index : index + max_run] for index in range(0, len(chunk), max_run)
        )

    return re.sub(r"\S+", split_run, text)


def wrapped_text_height(text: str, *, width: int, font: QFont) -> int:
    document = QTextDocument()
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
    document.setDefaultTextOption(option)
    document.setDefaultFont(font)
    document.setTextWidth(width)
    document.setPlainText(text)
    line_height = QFontMetrics(font).lineSpacing()
    return max(int(document.size().height()) + 2, line_height)


def fit_plain_text_edit_height(
    edit: QPlainTextEdit,
    *,
    min_height: int = DESC_EDIT_MIN_HEIGHT,
    max_height: int = DESC_EDIT_MAX_HEIGHT,
) -> None:
    """Resize QPlainTextEdit to fit wrapped content."""
    viewport_width = edit.viewport().width()
    if viewport_width <= 0:
        viewport_width = max(edit.width() - 16, 240)
    text = edit.toPlainText()
    if not text.strip():
        edit.setFixedHeight(min_height)
        return
    metrics = edit.fontMetrics()
    rect = metrics.boundingRect(
        0,
        0,
        viewport_width,
        0,
        int(Qt.TextFlag.TextWordWrap),
        text,
    )
    frame = edit.frameWidth() * 2
    margins = edit.contentsMargins().top() + edit.contentsMargins().bottom()
    height = int(rect.height() + frame + margins + 10)
    edit.setFixedHeight(max(min_height, min(max_height, height)))


def fit_wrapped_label_height(
    label: QLabel,
    text: str,
    *,
    width: int | None = None,
    max_height: int | None = None,
) -> int:
    """Resize word-wrapped QLabel to show full text without paint overflow."""
    if not text.strip():
        label.setMinimumHeight(0)
        label.setMaximumHeight(16777215)
        label.setMinimumWidth(0)
        label.setMaximumWidth(16777215)
        return 0
    available = width if width and width > 0 else max(label.width(), TIMER_DESC_TEXT_WIDTH)
    label.setWordWrap(True)
    label.setText(text)
    label.setFixedWidth(available)
    label.setMaximumWidth(available)
    needed = wrapped_text_height(text, width=available, font=label.font())
    if max_height is not None:
        label.setFixedHeight(min(needed, max_height))
        return needed
    if label.height() == needed:
        return needed
    label.setFixedHeight(needed)
    return needed
