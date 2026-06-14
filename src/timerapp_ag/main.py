from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .env_loader import load_env

from .app_info import DESKTOP_FILE_NAME, resolve_app_title
from .controller import AppController
from .main_window import MainWindow
from .single_instance import InstanceAcquireResult, SingleInstanceGuard
from .storage import Storage


def main() -> int:
    load_env()
    app_title = resolve_app_title()
    app = QApplication(sys.argv)
    app.setApplicationName(app_title)
    app.setOrganizationName("timerapp")
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

    controller = AppController(Storage())
    window = MainWindow(controller, app)
    instance_guard.bind_activation(window.bring_to_front)
    window.show()
    return app.exec()
