"""UI-обёртка для опционального слияния legacy-баз."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .legacy_merge import (
    LegacyMergePreview,
    clear_declined_fingerprint,
    find_legacy_merge_preview,
    format_legacy_merge_message,
    mark_legacy_merge_declined,
    should_prompt_on_startup,
)
from .storage import Storage


def offer_legacy_merge_on_startup(app_title: str, storage: Storage) -> bool:
    """Спросить при первом запуске после обнаружения старых баз. True, если выполнено слияние."""
    preview = find_legacy_merge_preview(storage.path)
    if preview is None or not should_prompt_on_startup(preview):
        return False
    return _confirm_and_merge(None, app_title, storage, preview)


def offer_legacy_merge_manual(parent, app_title: str, storage: Storage) -> bool:
    """Ручной запрос из меню настроек. True, если выполнено слияние."""
    preview = find_legacy_merge_preview(storage.path)
    if preview is None:
        QMessageBox.information(
            parent,
            app_title,
            "Других баз задач от прежних версий не найдено.",
        )
        return False
    return _confirm_and_merge(parent, app_title, storage, preview)


def _confirm_and_merge(
    parent,
    app_title: str,
    storage: Storage,
    preview: LegacyMergePreview,
) -> bool:
    answer = QMessageBox.question(
        parent,
        app_title,
        format_legacy_merge_message(preview),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer != QMessageBox.StandardButton.Yes:
        mark_legacy_merge_declined(preview)
        return False
    storage.consolidate_legacy_data_files()
    clear_declined_fingerprint()
    QMessageBox.information(
        parent,
        app_title,
        f"Базы объединены. Задач в текущей базе: {len(storage.load().tasks)}.",
    )
    return True
