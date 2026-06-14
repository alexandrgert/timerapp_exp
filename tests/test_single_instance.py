from __future__ import annotations

import uuid

from PySide6.QtNetwork import QLocalServer

from timerapp_ag.single_instance import InstanceAcquireResult, SingleInstanceGuard


def test_second_launch_is_not_primary(qapp) -> None:
    server_name = f"tasktimer-test-{uuid.uuid4()}"
    first = SingleInstanceGuard(server_name)
    second = SingleInstanceGuard(server_name)

    assert first.try_acquire_primary() is InstanceAcquireResult.PRIMARY
    assert second.try_acquire_primary() is InstanceAcquireResult.ALREADY_RUNNING


def test_activation_callback_on_second_launch(qapp) -> None:
    server_name = f"tasktimer-test-{uuid.uuid4()}"
    first = SingleInstanceGuard(server_name)
    assert first.try_acquire_primary() is InstanceAcquireResult.PRIMARY

    activated: list[bool] = []
    first.bind_activation(lambda: activated.append(True))

    second = SingleInstanceGuard(server_name)
    assert second.try_acquire_primary() is InstanceAcquireResult.ALREADY_RUNNING
    qapp.processEvents()
    assert activated == [True]


def test_pending_activation_flushed_on_bind(qapp) -> None:
    server_name = f"tasktimer-test-{uuid.uuid4()}"
    first = SingleInstanceGuard(server_name)
    assert first.try_acquire_primary() is InstanceAcquireResult.PRIMARY

    second = SingleInstanceGuard(server_name)
    assert second.try_acquire_primary() is InstanceAcquireResult.ALREADY_RUNNING
    qapp.processEvents()

    activated: list[bool] = []
    first.bind_activation(lambda: activated.append(True))
    assert activated == [True]


def test_listen_failure_returns_failed(qapp, monkeypatch) -> None:
    server_name = f"tasktimer-test-{uuid.uuid4()}"

    def fail_listen(self, _name: str) -> bool:
        self.setProperty("_test_error", "permission denied")
        return False

    def error_string(self) -> str:
        return "permission denied"

    monkeypatch.setattr(QLocalServer, "listen", fail_listen)
    monkeypatch.setattr(QLocalServer, "errorString", error_string)

    guard = SingleInstanceGuard(server_name)
    assert guard.try_acquire_primary() is InstanceAcquireResult.FAILED
    assert guard.last_error == "permission denied"
