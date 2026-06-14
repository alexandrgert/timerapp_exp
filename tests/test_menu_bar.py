from __future__ import annotations

from PySide6.QtWidgets import QApplication

from timerapp_ag.controller import AppController
from timerapp_ag.main_window import MainWindow
from timerapp_ag.storage import Storage


def test_menu_bar_has_exit_and_about(qapp: QApplication) -> None:
    controller = AppController(Storage())
    window = MainWindow(controller, qapp)

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert "Настройки" in menu_titles
    assert "Выход" in menu_titles
    assert "О программе" in menu_titles

    window.close()
