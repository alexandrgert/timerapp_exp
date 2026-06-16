"""Резервное копирование данных при штатном и аварийном завершении."""
from __future__ import annotations

import atexit
import logging
import os
import signal

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .controller import AppController
from .webdav_sync import sync_webdav_on_shutdown

logger = logging.getLogger(__name__)


def _terminal_signals_disabled() -> bool:
    return os.environ.get("TASKTIMER_TERMINAL_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_shutdown_backup(controller: AppController, *, reason: str = "shutdown") -> None:
    """Сохранить состояние, локальный backup и опционально WebDAV (для тестов и shutdown)."""
    try:
        controller.save()
    except Exception as exc:
        logger.exception("Shutdown save failed: %s", exc)
    try:
        controller.storage.create_backup(reason)
    except Exception as exc:
        logger.exception("Shutdown backup failed: %s", exc)
    try:
        outcome = sync_webdav_on_shutdown(controller.storage)
        if outcome.error:
            logger.error("Shutdown WebDAV sync failed: %s", outcome.error)
    except Exception as exc:
        logger.exception("Shutdown WebDAV sync raised: %s", exc)


def register_shutdown_backup(app: QApplication, controller: AppController) -> None:
    ran = False

    def shutdown_backup() -> None:
        nonlocal ran
        if ran:
            return
        ran = True
        run_shutdown_backup(controller)

    def _quit_application() -> None:
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.quit()

    def shutdown_backup_and_quit() -> None:
        shutdown_backup()
        _quit_application()

    def signal_backup(signum: int, _frame: object) -> None:
        logger.info("Received signal %s, scheduling shutdown", signum)
        qt_app = QApplication.instance()
        if qt_app is None:
            shutdown_backup()
            return
        # Не вызывать Qt из обработчика сигнала — только через event loop.
        QTimer.singleShot(0, shutdown_backup_and_quit)

    app.aboutToQuit.connect(shutdown_backup)
    atexit.register(shutdown_backup)

    if _terminal_signals_disabled():
        logger.debug("TASKTIMER_TERMINAL_MODE: SIGINT/SIGTERM handlers not installed")
        return

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, signal_backup)
        except (AttributeError, ValueError, OSError) as exc:
            logger.debug("Cannot install handler for %s: %s", sig, exc)
