from __future__ import annotations

import os
from pathlib import Path

from timerapp_ag import env_loader


def test_load_env_reads_repo_dotenv(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("BITRIX24_HOOK_URL=https://example.test/hook/\n", encoding="utf-8")
    monkeypatch.delenv("BITRIX24_HOOK_URL", raising=False)
    monkeypatch.setattr(env_loader, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(env_loader, "user_config_env_path", lambda: None)

    env_loader.load_env()

    assert os.environ["BITRIX24_HOOK_URL"] == "https://example.test/hook/"
