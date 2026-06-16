from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from timerapp_ag.shutdown_backup import run_shutdown_backup


def test_run_shutdown_backup_saves_and_creates_backup(tmp_path: Path) -> None:
    data_path = tmp_path / "data.json"
    storage = MagicMock()
    storage.path = data_path
    storage.create_backup = MagicMock(return_value=tmp_path / "backups" / "data.json")

    controller = MagicMock()
    controller.storage = storage

    run_shutdown_backup(controller, reason="shutdown-test")

    controller.save.assert_called_once()
    storage.create_backup.assert_called_once_with("shutdown-test")
