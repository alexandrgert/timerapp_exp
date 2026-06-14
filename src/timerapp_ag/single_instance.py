"""Запуск только одного экземпляра приложения (QLocalServer / QLocalSocket)."""
from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "tasktimer-link-b24.single"
ACTIVATE_MESSAGE = b"activate"


class InstanceAcquireResult(Enum):
    PRIMARY = "primary"
    ALREADY_RUNNING = "already_running"
    FAILED = "failed"


class SingleInstanceGuard:
    """Первый экземпляр слушает сокет; повторный запуск шлёт ping и завершается."""

    def __init__(self, server_name: str = SERVER_NAME) -> None:
        self._server_name = server_name
        self._server: QLocalServer | None = None
        self._on_activate: Callable[[], None] | None = None
        self._pending_activate = False
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    def bind_activation(self, callback: Callable[[], None]) -> None:
        self._on_activate = callback
        if self._pending_activate:
            self._pending_activate = False
            callback()

    def try_acquire_primary(self) -> InstanceAcquireResult:
        socket = QLocalSocket()
        socket.connectToServer(self._server_name)
        if socket.waitForConnected(300):
            socket.write(ACTIVATE_MESSAGE)
            socket.flush()
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            return InstanceAcquireResult.ALREADY_RUNNING

        QLocalServer.removeServer(self._server_name)
        self._server = QLocalServer()
        if not self._server.listen(self._server_name):
            self._last_error = self._server.errorString() or "неизвестная ошибка"
            self._server = None
            return InstanceAcquireResult.FAILED
        self._server.newConnection.connect(self._handle_connection)
        return InstanceAcquireResult.PRIMARY

    def _handle_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.waitForReadyRead(100)
        socket.readAll()
        socket.disconnectFromServer()
        if self._on_activate is not None:
            self._on_activate()
        else:
            self._pending_activate = True
