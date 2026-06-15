from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .env_loader import load_env

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from .app_info import APP_TITLE_BASE, DESKTOP_FILE_NAME, STORAGE_ORG, resolve_app_title
from .controller import AppController
from .main_window import MainWindow
from .shutdown_backup import register_shutdown_backup
from .legacy_merge_ui import offer_legacy_merge_on_startup
from .single_instance import InstanceAcquireResult, SingleInstanceGuard
from .storage import Storage


def main() -> int:
    load_env()
    app_title = resolve_app_title()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE_BASE)
    app.setOrganizationName(STORAGE_ORG)
    app.setDesktopFileName(DESKTOP_FILE_NAME)
    app.setQuitOnLastWindowClosed(False)

    instance_guard = SingleInstanceGuard()
    acquire_result = instance_guard.try_acquire_primary()
    if acquire_result is InstanceAcquireResult.ALREADY_RUNNING:
        QMessageBox.information(
            None,
            app_title,
            "Приложение уже запущено.",
        )
        return 0
    if acquire_result is InstanceAcquireResult.FAILED:
        QMessageBox.critical(
            None,
            app_title,
            f"Не удалось запустить приложение.\n\n{instance_guard.last_error}",
        )
        return 1

    storage = Storage()
    merged_on_startup = offer_legacy_merge_on_startup(app_title, storage)
    controller = AppController(storage)
    if merged_on_startup:
        controller.reload_state_from_storage()
    register_shutdown_backup(app, controller)
    window = MainWindow(controller, app)
    instance_guard.bind_activation(window.bring_to_front)
    window.show()
    return app.exec()
