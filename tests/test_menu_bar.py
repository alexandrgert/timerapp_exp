from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from timerapp_ag.controller import AppController
from timerapp_ag.main_window import AboutDialog, MainWindow
from timerapp_ag.storage import Storage
from timerapp_ag.update_check import UpdateCheckResult


def test_menu_bar_has_exit_and_about(qapp: QApplication) -> None:
    controller = AppController(Storage())
    window = MainWindow(controller, qapp)

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert "Настройки" in menu_titles
    assert "Выход" in menu_titles
    assert "О программе" in menu_titles

    window.close()


def test_about_dialog_has_update_check_button(
    qapp: QApplication, controller: AppController
) -> None:
    dialog = AboutDialog(controller)
    assert dialog.update_check_now_button.text() == "Проверить сейчас"
    assert dialog.update_check_now_button.isEnabled()
    dialog.close()


def test_about_dialog_check_now_uses_github_releases(
    qapp: QApplication,
    controller: AppController,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "timerapp_ag.app_prefs.app_prefs_path", lambda: tmp_path / "app-prefs.json"
    )
    called: dict[str, object] = {}

    def fake_check(**kwargs: object) -> UpdateCheckResult:
        called.update(kwargs)
        return UpdateCheckResult(
            ok=True,
            current_version="0.11.1",
            latest=None,
            update_available=False,
        )

    monkeypatch.setattr("timerapp_ag.main_window.check_for_update", fake_check)
    dialog = AboutDialog(controller)
    dialog.update_check_now_button.click()
    dialog._manual_update_check.wait(5000)
    qapp.processEvents()
    assert called.get("respect_dismissed") is False
    assert "timerapp_exp" in str(called.get("github_repo"))
    assert "актуальн" in dialog.update_check_status.text().lower()
    dialog.close()
