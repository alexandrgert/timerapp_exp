from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from timerapp_ag.controller import AppController
from timerapp_ag.models import Session, Task, TaskStatus, make_id
from timerapp_ag.storage import Storage
from timerapp_ag.webdav_client import WebDavClient, WebDavError
from timerapp_ag.webdav_config import WebDavConfig
from timerapp_ag.webdav_sync import (
    _remote_payload_hash,
    _upload_payload,
    pull_and_merge,
    push_local,
)
from timerapp_ag.webdav_meta import RemoteSyncMeta, content_hash, new_meta


@pytest.fixture
def webdav_config() -> WebDavConfig:
    return WebDavConfig(
        enabled=False,
        url="https://cloud.example.com/dav/",
        username="alex",
        password="secret",
        remote_path="tasktimer/data.json",
    )


def test_pull_without_enabled_flag(tmp_path: Path, webdav_config: WebDavConfig) -> None:
    storage = Storage(path=tmp_path / "data.json", migrate_legacy=False)
    storage.save(storage.load())
    remote_payload = json.dumps(
        {"tasks": [{"id": "remote", "day": "2026-06-15", "title": "Из облака"}], "ui": {}}
    ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        method = request.get_method()
        response = MagicMock()
        response.status = 200
        response.read.return_value = remote_payload
        response.headers.items.return_value = []
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: None
        return response

    with patch("timerapp_ag.webdav_client.urllib.request.urlopen", side_effect=fake_urlopen):
        with patch.object(WebDavClient, "exists", return_value=True):
            with patch("timerapp_ag.webdav_sync.mark_webdav_sync_ok"):
                outcome = pull_and_merge(storage, webdav_config, require_enabled=False)

    assert outcome.state is not None
    assert {task.id for task in outcome.state.tasks} == {"remote"}


def test_webdav_exists_uses_status_code_404(webdav_config: WebDavConfig) -> None:
    client = WebDavClient(webdav_config)
    with patch.object(client, "_request", side_effect=WebDavError("missing", status_code=404)):
        assert client.exists() is False


def test_webdav_exists_head_405_falls_back_to_get(webdav_config: WebDavConfig) -> None:
    client = WebDavClient(webdav_config)
    calls: list[str] = []

    def fake_request(method: str, url: str, **kwargs: object) -> tuple[int, bytes, dict[str, str]]:
        calls.append(method)
        if method == "HEAD":
            raise WebDavError("method not allowed", status_code=405)
        if method == "GET":
            return 206, b"x", {}
        raise AssertionError(f"Unexpected method {method}")

    with patch.object(client, "_request", side_effect=fake_request):
        assert client.exists() is True
    assert calls == ["HEAD", "GET"]


def test_apply_loaded_state_rebuilds_reminder_after_running_merge(storage: Storage) -> None:
    payload = {
        "tasks": [
            {
                "id": "t1",
                "day": "2026-06-15",
                "title": "Remote running",
                "status": "running",
                "sessions": [{"id": "s1", "started_at": datetime.now().isoformat()}],
            }
        ],
        "ui": {"reminder_interval_minutes": 40},
    }
    storage.path.write_text(json.dumps(payload), encoding="utf-8")

    controller = AppController(storage)
    controller.pending_confirmation_task_id = "stale"
    controller.next_reminder_at = datetime.now() - timedelta(hours=1)
    controller.reload_state_from_storage()

    assert controller.pending_confirmation_task_id is None
    assert controller.next_reminder_at is not None
    assert controller.active_task() is not None


def test_push_pull_before_push_merges_remote(tmp_path: Path, webdav_config: WebDavConfig) -> None:
    storage = Storage(path=tmp_path / "data.json", migrate_legacy=False)
    local = {
        "tasks": [{"id": "local", "day": "2026-06-15", "title": "Local", "status": "open", "sessions": []}],
        "ui": {},
    }
    storage.path.write_text(json.dumps(local), encoding="utf-8")
    remote_payload = json.dumps(
        {"tasks": [{"id": "remote", "day": "2026-06-15", "title": "Remote", "status": "open", "sessions": []}], "ui": {}}
    ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        method = request.get_method()
        response = MagicMock()
        response.status = 204 if method == "PUT" else 200
        response.read.return_value = remote_payload if method == "GET" else b""
        response.headers.items.return_value = []
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: None
        return response

    with patch("timerapp_ag.webdav_client.urllib.request.urlopen", side_effect=fake_urlopen):
        with patch.object(WebDavClient, "exists", return_value=True):
            with patch("timerapp_ag.webdav_sync.mark_webdav_sync_ok"):
                outcome = push_local(storage, webdav_config, require_enabled=False)

    assert outcome.state is not None
    titles = {task.title for task in outcome.state.tasks}
    assert titles == {"Local", "Remote"}


def test_upload_meta_retries_after_transient_failure(webdav_config: WebDavConfig) -> None:
    client = WebDavClient(webdav_config)
    meta_attempts = 0

    def fake_upload(url: str, payload: bytes, **kwargs: object) -> None:
        nonlocal meta_attempts
        if url.endswith(".sync-meta.json"):
            meta_attempts += 1
            if meta_attempts == 1:
                raise WebDavError("server busy", status_code=503)

    with patch.object(client, "upload", side_effect=fake_upload):
        with patch("timerapp_ag.webdav_sync.time.sleep"):
            meta = _upload_payload(client, webdav_config, b"{}")

    assert meta.content_hash
    assert meta_attempts == 2


def test_remote_payload_hash_uses_file_when_meta_mismatches() -> None:
    payload = b'{"tasks":[]}'
    file_hash = content_hash(payload)
    stale_meta = RemoteSyncMeta(
        content_hash="0" * 64,
        revision="stale",
        updated_at="2026-06-15T12:00:00",
        device_id="dev",
    )
    assert _remote_payload_hash(payload, stale_meta) == file_hash


def test_remote_payload_hash_prefers_matching_meta() -> None:
    payload = b'{"tasks":[]}'
    digest = content_hash(payload)
    meta = new_meta(payload, "dev")
    assert _remote_payload_hash(payload, meta) == digest


def test_upload_payload_retries_full_cycle_on_meta_failure(webdav_config: WebDavConfig) -> None:
    client = WebDavClient(webdav_config)
    data_uploads = 0

    def fake_upload(url: str, payload: bytes, **kwargs: object) -> None:
        nonlocal data_uploads
        if url.endswith(".sync-meta.json"):
            raise WebDavError("meta failed", status_code=503)
        data_uploads += 1

    with patch.object(client, "upload", side_effect=fake_upload):
        with patch("timerapp_ag.webdav_sync.time.sleep"):
            with pytest.raises(WebDavError, match="sync-meta"):
                _upload_payload(client, webdav_config, b"{}")

    assert data_uploads == 2
