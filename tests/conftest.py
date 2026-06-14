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


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """Storage backed by an isolated temp data.json (no real AppData writes)."""
    return Storage(path=tmp_path / "data.json")


@pytest.fixture
def controller(storage: Storage) -> AppController:
    return AppController(storage)
