from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from timerapp_ag.controller import AppController
from timerapp_ag.storage import Storage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def isolated_bitrix_secrets(tmp_path: Path, monkeypatch):
    path = tmp_path / "bitrix-secrets.json"
    monkeypatch.setattr("timerapp_ag.platform_paths.bitrix_secrets_path", lambda: path)
    return path


@pytest.fixture(autouse=True)
def isolated_webdav_config(tmp_path: Path, monkeypatch):
    """Изолированный webdav.json и отключение WEBDAV_* из окружения в тестах."""
    path = tmp_path / "webdav.json"
    monkeypatch.setattr("timerapp_ag.platform_paths.webdav_config_path", lambda: path)
    for key in (
        "WEBDAV_ENABLED",
        "WEBDAV_URL",
        "WEBDAV_USERNAME",
        "WEBDAV_USER",
        "WEBDAV_PASSWORD",
        "WEBDAV_REMOTE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    return path


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """Storage backed by an isolated temp data.json (no real AppData writes)."""
    return Storage(path=tmp_path / "data.json")


@pytest.fixture
def controller(storage: Storage) -> AppController:
    return AppController(storage)
