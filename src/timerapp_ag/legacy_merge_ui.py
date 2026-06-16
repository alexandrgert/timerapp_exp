"""UI-обёртка для опционального слияния legacy-баз."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .legacy_merge import (
    LegacyMergePreview,
    clear_declined_fingerprint,
    find_legacy_merge_preview,
    format_legacy_merge_details,
    format_legacy_merge_summary,
    mark_legacy_merge_declined,
    should_prompt_on_startup,
)
from .storage import Storage


def offer_legacy_merge_on_startup(app_title: str, storage: Storage) -> bool:
    """Спросить при первом запуске после обнаружения старых баз. True, если выполнено слияние."""
    preview = find_legacy_merge_preview(storage.path)
    if preview is None or not should_prompt_on_startup(preview):
        return False
    return _confirm_and_merge(
        None,
        app_title,
        storage,
        preview,
        record_decline_on_cancel=True,
    )


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
    return _confirm_and_merge(
        parent,
        app_title,
        storage,
        preview,
        record_decline_on_cancel=False,
    )


def _confirm_and_merge(
    parent,
    app_title: str,
    storage: Storage,
    preview: LegacyMergePreview,
    *,
    record_decline_on_cancel: bool,
) -> bool:
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(app_title)
    dialog.setText(format_legacy_merge_summary(preview))
    dialog.setDetailedText(format_legacy_merge_details(preview))
    dialog.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    dialog.setDefaultButton(QMessageBox.StandardButton.Yes)
    answer = dialog.exec()

    if answer != QMessageBox.StandardButton.Yes:
        if record_decline_on_cancel:
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
