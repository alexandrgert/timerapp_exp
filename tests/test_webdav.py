from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from timerapp_ag.storage import Storage
from timerapp_ag.webdav_client import WebDavClient, WebDavError
from timerapp_ag.webdav_config import WebDavConfig, save_webdav_config, webdav_config_path
from timerapp_ag.webdav_sync import pull_and_merge, push_local


@pytest.fixture
def webdav_config() -> WebDavConfig:
    return WebDavConfig(
        enabled=True,
        url="https://cloud.example.com/dav/",
        username="alex",
        password="secret",
        remote_path="tasktimer/data.json",
    )


def test_webdav_config_round_trip(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "webdav.json"
    monkeypatch.setattr("timerapp_ag.platform_paths.webdav_config_path", lambda: path)
    config = WebDavConfig(enabled=True, url="https://x/", username="u", password="p")
    save_webdav_config(config)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["url"] == "https://x/"
    assert loaded["password"] == "p"
    assert loaded["device_id"]


def test_remote_url_joins_base_and_path(webdav_config: WebDavConfig) -> None:
    assert webdav_config.remote_url() == "https://cloud.example.com/dav/tasktimer/data.json"


def test_meta_remote_url_joins_base_and_path(webdav_config: WebDavConfig) -> None:
    assert (
        webdav_config.meta_remote_url()
        == "https://cloud.example.com/dav/tasktimer/data.sync-meta.json"
    )


def test_pull_and_merge_downloads_remote(tmp_path: Path, webdav_config: WebDavConfig) -> None:
    storage = Storage(path=tmp_path / "data.json", migrate_legacy=False)
    storage.save(storage.load())
    remote_payload = json.dumps(
        {"tasks": [{"id": "remote", "day": "2026-06-15", "title": "Из облака"}], "ui": {}}
    ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        method = request.get_method()
        if method == "GET":
            response = MagicMock()
            response.status = 200
            response.read.return_value = remote_payload
            response.headers.items.return_value = []
            response.__enter__ = lambda self: response
            response.__exit__ = lambda *args: None
            return response
        raise AssertionError(f"Unexpected method {method}")

    with patch("timerapp_ag.webdav_client.urllib.request.urlopen", side_effect=fake_urlopen):
        with patch.object(WebDavClient, "exists", return_value=True):
            with patch("timerapp_ag.webdav_sync.mark_webdav_sync_ok"):
                outcome = pull_and_merge(storage, webdav_config)

    assert outcome.state is not None
    assert {task.id for task in outcome.state.tasks} == {"remote"}
    reloaded = json.loads(storage.path.read_text(encoding="utf-8"))
    assert reloaded["tasks"][0]["title"] == "Из облака"


def test_push_local_uploads_file(tmp_path: Path, webdav_config: WebDavConfig) -> None:
    storage = Storage(path=tmp_path / "data.json", migrate_legacy=False)
    storage.save(storage.load())
    calls: list[str] = []

    def fake_urlopen(request, timeout=0):
        method = request.get_method()
        calls.append(method)
        response = MagicMock()
        response.status = 201 if method == "MKCOL" else 204
        response.read.return_value = b""
        response.headers.items.return_value = []
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: None
        return response

    with patch("timerapp_ag.webdav_client.urllib.request.urlopen", side_effect=fake_urlopen):
        with patch.object(WebDavClient, "exists", return_value=False):
            with patch("timerapp_ag.webdav_sync.mark_webdav_sync_ok"):
                push_local(storage, webdav_config)

    assert "PUT" in calls


def test_webdav_client_requires_configuration() -> None:
    with pytest.raises(WebDavError):
        WebDavClient(WebDavConfig())
