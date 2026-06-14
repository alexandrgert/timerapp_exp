from __future__ import annotations

from timerapp_ag.main import main
from timerapp_ag.single_instance import InstanceAcquireResult


def test_main_already_running_shows_message_and_exits(qapp, monkeypatch) -> None:
    shown: list[tuple[object, ...]] = []

    monkeypatch.setattr("timerapp_ag.main.load_env", lambda: None)
    monkeypatch.setattr("timerapp_ag.main.QApplication", lambda _argv: qapp)
    monkeypatch.setattr(
        "timerapp_ag.main.SingleInstanceGuard.try_acquire_primary",
        lambda self: InstanceAcquireResult.ALREADY_RUNNING,
    )
    monkeypatch.setattr(
        "timerapp_ag.main.QMessageBox.information",
        lambda *args, **kwargs: shown.append(args),
    )
    monkeypatch.setattr(
        "timerapp_ag.main.QMessageBox.critical",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("critical should not be called")),
    )

    assert main() == 0
    assert len(shown) == 1
    assert shown[0][2] == "Приложение уже запущено."


def test_main_listen_failure_shows_error_and_exits(qapp, monkeypatch) -> None:
    critical: list[tuple[object, ...]] = []

    class FailingGuard:
        last_error = "permission denied"

        def try_acquire_primary(self) -> InstanceAcquireResult:
            return InstanceAcquireResult.FAILED

        def bind_activation(self, _callback: object) -> None:
            return None

    monkeypatch.setattr("timerapp_ag.main.load_env", lambda: None)
    monkeypatch.setattr("timerapp_ag.main.QApplication", lambda _argv: qapp)
    monkeypatch.setattr("timerapp_ag.main.SingleInstanceGuard", FailingGuard)
    monkeypatch.setattr(
        "timerapp_ag.main.QMessageBox.critical",
        lambda *args, **kwargs: critical.append(args),
    )
    monkeypatch.setattr(
        "timerapp_ag.main.QMessageBox.information",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("information should not be called")),
    )

    assert main() == 1
    assert len(critical) == 1
    assert "permission denied" in str(critical[0][2])
