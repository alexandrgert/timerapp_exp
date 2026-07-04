from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from timerapp_ag.app_info import APP_TITLE_BASE, STORAGE_ORG
from timerapp_ag import platform_paths
from timerapp_ag.domain.constants import SCHEMA_VERSION
from timerapp_ag.domain.state import AppState
from timerapp_ag.storage import Storage


def test_config_dir_under_tmp_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    path = platform_paths.config_dir()
    assert path.is_absolute()
    assert STORAGE_ORG in path.as_posix().lower()


def test_stable_data_path_uses_org_and_title(tmp_path: Path, monkeypatch) -> None:
    share = tmp_path / "share" / STORAGE_ORG
    monkeypatch.setattr(
        platform_paths,
        "data_share_roots",
        lambda: [share.resolve()],
    )
    data_path = platform_paths.stable_data_path()
    assert data_path.name == "data.json"
    assert data_path.parent.name == APP_TITLE_BASE


def test_bitrix_and_webdav_secrets_under_config_dir(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "cfg"
    monkeypatch.setattr(platform_paths, "config_dir", lambda: cfg)
    monkeypatch.setattr(platform_paths, "bitrix_secrets_path", lambda: cfg / "bitrix.json")
    monkeypatch.setattr(platform_paths, "webdav_config_path", lambda: cfg / "webdav.json")
    assert platform_paths.bitrix_secrets_path() == cfg / "bitrix.json"
    assert platform_paths.webdav_config_path() == cfg / "webdav.json"
    assert platform_paths.user_env_path() == cfg / ".env"


@pytest.mark.parametrize(
    "fake_platform",
    [
        platform_paths.Platform.WINDOWS,
        platform_paths.Platform.MACOS,
        platform_paths.Platform.LINUX,
    ],
)
def test_local_data_home_per_platform(
    tmp_path: Path,
    monkeypatch,
    fake_platform: platform_paths.Platform,
) -> None:
    monkeypatch.setattr(platform_paths, "detect_platform", lambda: fake_platform)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    if fake_platform is platform_paths.Platform.WINDOWS:
        expected = tmp_path / "AppData" / "Local"
        monkeypatch.setenv("LOCALAPPDATA", str(expected))
    elif fake_platform is platform_paths.Platform.MACOS:
        expected = tmp_path / "Library" / "Application Support"
    else:
        expected = tmp_path / ".local" / "share"

    assert platform_paths._local_data_home().resolve() == expected.resolve()


def test_local_data_home_uses_xdg_data_home_on_linux(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(platform_paths, "detect_platform", lambda: platform_paths.Platform.LINUX)
    xdg = tmp_path / "xdg-data"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    assert platform_paths._local_data_home() == xdg


@pytest.mark.skipif(sys.platform != "linux", reason="linux-specific XDG fallback")
def test_linux_data_share_roots_includes_local_share(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    roots = platform_paths.data_share_roots()
    assert any(STORAGE_ORG in root.as_posix() for root in roots)


def test_saved_state_matches_schema_shape(tmp_path: Path) -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/schemas/data.schema.json").read_text(
            encoding="utf-8"
        )
    )
    storage = Storage(path=tmp_path / "data.json", migrate_legacy=False)
    state = AppState()
    state.ui["schema_version"] = SCHEMA_VERSION
    storage.save(state)
    payload = json.loads(storage.path.read_text(encoding="utf-8"))

    assert set(payload.keys()) == set(schema["required"])
    assert isinstance(payload["tasks"], list)
    assert isinstance(payload["ui"], dict)
    assert payload["ui"]["schema_version"] == SCHEMA_VERSION
    assert "webhook_url" not in json.dumps(payload["ui"])
