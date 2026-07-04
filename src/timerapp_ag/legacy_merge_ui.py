"""UI-обёртка для опционального слияния legacy-баз."""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox

from . import platform_paths
from .legacy_merge import (
    LegacyMergePreview,
    add_configured_legacy_location,
    clear_declined_fingerprint,
    find_legacy_merge_preview,
    format_legacy_merge_details,
    format_legacy_merge_summary,
    list_configured_legacy_locations,
    mark_legacy_merge_declined,
    remove_configured_legacy_location,
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
        answer = QMessageBox.question(
            parent,
            app_title,
            "Других баз задач автоматически не найдено.\n\n"
            "Указать каталог или файл data.json старой версии?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes and configure_legacy_data_location(parent, app_title):
            preview = find_legacy_merge_preview(storage.path)
            if preview is not None:
                return _confirm_and_merge(
                    parent,
                    app_title,
                    storage,
                    preview,
                    record_decline_on_cancel=False,
                )
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


def configure_legacy_data_location(parent, app_title: str) -> bool:
    """Выбор каталога/файла старой базы. True, если путь сохранён."""
    start_dir = str(platform_paths._local_data_home())
    file_path, _ = QFileDialog.getOpenFileName(
        parent,
        "Файл data.json старой версии",
        start_dir,
        "JSON (*.json);;All files (*)",
    )
    chosen = file_path.strip()
    if not chosen:
        directory = QFileDialog.getExistingDirectory(
            parent,
            "Каталог данных старой версии (data.json внутри)",
            start_dir,
        )
        chosen = directory.strip()
    if not chosen:
        return False

    data_path, error = add_configured_legacy_location(chosen)
    if data_path is None:
        QMessageBox.warning(parent, app_title, error)
        return False

    locations = list_configured_legacy_locations()
    lines = "\n".join(f"• {item}" for item in locations)
    QMessageBox.information(
        parent,
        app_title,
        f"Сохранён каталог старой версии:\n{data_path.parent}\n\n"
        f"Все указанные каталоги:\n{lines}\n\n"
        "Объединение — пункт меню «Объединить базы старых версий…».",
    )
    return True


def manage_legacy_data_locations(parent, app_title: str) -> None:
    """Просмотр и правка списка каталогов старых версий."""
    locations = list_configured_legacy_locations()
    if not locations:
        if configure_legacy_data_location(parent, app_title):
            QMessageBox.information(
                parent,
                app_title,
                "Каталог старой версии сохранён. Объединение — в пункте «Объединить базы старых версий…».",
            )
        return

    lines = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(locations))
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(app_title)
    dialog.setText(f"Каталоги старых версий:\n{lines}")
    add_button = dialog.addButton("Добавить каталог…", QMessageBox.ButtonRole.ActionRole)
    remove_button = dialog.addButton("Удалить каталог…", QMessageBox.ButtonRole.DestructiveRole)
    close_button = dialog.addButton("Закрыть", QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(close_button)
    dialog.exec()

    clicked = dialog.clickedButton()
    if clicked is add_button:
        configure_legacy_data_location(parent, app_title)
    elif clicked is remove_button:
        _remove_configured_legacy_location(parent, app_title, locations)


def _remove_configured_legacy_location(parent, app_title: str, locations: list[str]) -> None:
    if len(locations) == 1:
        remove_configured_legacy_location(locations[0])
        QMessageBox.information(parent, app_title, "Каталог удалён из списка.")
        return

    pick, ok = _pick_location_index(parent, locations)
    if ok and pick is not None:
        remove_configured_legacy_location(locations[pick])
        QMessageBox.information(parent, app_title, "Каталог удалён из списка.")


def _pick_location_index(parent, locations: list[str]) -> tuple[int | None, bool]:
    from PySide6.QtWidgets import QInputDialog

    labels = [f"{index + 1}. {path}" for index, path in enumerate(locations)]
    text, ok = QInputDialog.getItem(
        parent,
        "Удалить каталог",
        "Какой каталог убрать из списка?",
        labels,
        0,
        False,
    )
    if not ok:
        return None, False
    index = labels.index(text)
    return index, True


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
