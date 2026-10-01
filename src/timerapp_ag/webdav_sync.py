"""Causal WebDAV v2; all write paths use conditional pull/merge/PUT."""
from __future__ import annotations
import json
import hashlib
from uuid import uuid4
from dataclasses import dataclass
from . import sync_protocol as protocol
from .storage import AppState, Storage
from .webdav_client import WebDavClient, WebDavError
from .webdav_config import (WebDavConfig, load_webdav_config, mark_webdav_sync_error,
    mark_webdav_sync_ok, save_webdav_config, save_webdav_pending_notice)
from .webdav_meta import content_hash
from .webdav_sync_log import append_entry

@dataclass
class SyncOutcome:
    state: AppState | None = None
    error: str = ""
    conflict_detected: bool = False
    notice: str = ""
    uploaded_tasks: int = 0
    downloaded_tasks: int = 0

@dataclass
class RemoteCheckOutcome:
    remote_changed: bool = False
    remote_hash: str = ""
    error: str = ""


def _remote(client, config):
    try:
        payload, etag = client.download_versioned(config.remote_url() + '.v2.json')
    except WebDavError as exc:
        if exc.status_code == 404:
            return protocol.empty_document(), None
        raise
    try:
        return protocol.validate_document(json.loads(payload)), etag
    except (ValueError, UnicodeError) as exc:
        raise WebDavError('Некорректный или неподдерживаемый файл синхронизации v2') from exc


def _exchange(storage, config, *, upload, require_enabled, log_op):
    if require_enabled and not config.enabled:
        raise WebDavError('Синхронизация WebDAV отключена')
    try:
        client = WebDavClient(config)
        storage.enable_sync_v2()
        migration_key = hashlib.sha256((config.remote_url() + "\n" + config.username).encode()).hexdigest()
        for attempt in range(3):
            remote, etag = _remote(client, config)
            # Network is outside the local transaction; merge rereads latest disk state.
            legacy_tasks = None
            local = storage.load()
            if etag is None and migration_key not in local.ui.get("sync_v2_remote_imports", []):
                try:
                    legacy_bytes = client.download(config.remote_url())
                except WebDavError as exc:
                    if exc.status_code != 404:
                        raise
                else:
                    legacy = json.loads(legacy_bytes)
                    if not isinstance(legacy, dict) or not isinstance(legacy.get("tasks"), list) or legacy.get("format") or legacy.get("schemaVersion", 1) != 1:
                        raise ValueError("Неподдерживаемый старый файл WebDAV")
                    # UI may contain historic secrets: only task data is imported/backed up.
                    legacy_tasks = [t.to_dict() for t in AppState.from_dict({"tasks": legacy["tasks"]}).tasks]
                    remote = protocol.import_legacy(legacy_tasks, "legacy-remote-" + uuid4().hex)
            state = storage.merge_sync_v2(remote, migration_key=migration_key, legacy_tasks=legacy_tasks)
            projection = protocol.project_tasks(state.sync_v2)
            payload = json.dumps(state.sync_v2, ensure_ascii=False, separators=(',', ':')).encode()
            if upload:
                try:
                    client.upload_conditional(config.remote_url() + '.v2.json', payload, etag=etag)
                except WebDavError as exc:
                    if exc.status_code == 412 and attempt < 2:
                        continue
                    raise
            state = storage.load()  # Include edits committed while PUT was in flight.
            conflicts = protocol.project_document(state.sync_v2)['conflicts']
            notice = ('Синхронизация v2: обновите все устройства. Старые версии используют отдельный файл.')
            if conflicts:
                notice += f' Требуют выбора: {len(conflicts)} конфликтов.'
            result = SyncOutcome(state=state, conflict_detected=bool(conflicts), notice=notice,
                uploaded_tasks=len(projection['tasks']) if upload else 0,
                downloaded_tasks=len(protocol.project_tasks(remote)['tasks']))
            mark_webdav_sync_ok(config, remote_hash=content_hash(payload), had_conflict=bool(conflicts))
            append_entry(log_op, uploaded_tasks=result.uploaded_tasks, downloaded_tasks=result.downloaded_tasks, ok=True, error='')
            return result
        raise WebDavError('Сервер изменяется одновременно: повторите синхронизацию позже')
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        error = WebDavError(str(exc))
        append_entry(log_op, uploaded_tasks=0, downloaded_tasks=0, ok=False, error=str(error))
        raise error from exc
    except WebDavError as exc:
        append_entry(log_op, uploaded_tasks=0, downloaded_tasks=0, ok=False, error=str(exc))
        raise


def pull_and_merge(storage, config=None, *, require_enabled=True, log_op='pull'):
    return _exchange(storage, config or load_webdav_config(), upload=False, require_enabled=require_enabled, log_op=log_op)


def push_local(storage, config=None, *, require_enabled=True, log_op='push'):
    return _exchange(storage, config or load_webdav_config(), upload=True, require_enabled=require_enabled, log_op=log_op)


def push_merged_state(storage, config=None, *, require_enabled=True, log_op=None):
    return push_local(storage, config, require_enabled=require_enabled, log_op=log_op or 'push')


def push_local_upload_only(storage, config=None, *, require_enabled=True, log_op='push_upload_only'):
    # Retained API for old settings; deliberately no unsafe upload-only mode in v2.
    return push_local(storage, config, require_enabled=require_enabled, log_op=log_op)


def sync_webdav_now(storage, config=None, *, require_enabled=False):
    config = config or load_webdav_config()
    try:
        return push_local(storage, config, require_enabled=require_enabled, log_op='sync')
    except WebDavError as exc:
        mark_webdav_sync_error(config, str(exc))
        return SyncOutcome(error=str(exc))


def _automatic(storage, *, mode):
    config = load_webdav_config()
    if not config.enabled or (mode == 'startup' and not config.sync_on_startup) or (mode == 'shutdown' and not config.sync_on_shutdown):
        return SyncOutcome()
    try:
        outcome = (pull_and_merge if mode == 'startup' else push_local)(storage, config, log_op=mode)
        if mode == 'shutdown' and outcome.conflict_detected:
            save_webdav_pending_notice(outcome.notice)
        return outcome
    except WebDavError as exc:
        mark_webdav_sync_error(config, str(exc))
        return SyncOutcome(error=str(exc))


def sync_webdav_on_startup(storage): return _automatic(storage, mode='startup')
def sync_webdav_on_shutdown(storage): return _automatic(storage, mode='shutdown')
def sync_webdav_on_reconnect(storage): return _automatic(storage, mode='reconnect')
def save_webdav_settings(config): save_webdav_config(config)


def test_webdav_connection(config):
    client = WebDavClient(config)
    client.test_connection()
    return 'Подключение успешно. Для v2 сервер должен поддерживать ETag и условную запись.'


def check_remote_changes(storage, config=None, *, require_enabled=True):
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        return RemoteCheckOutcome()
    try:
        remote, _ = _remote(WebDavClient(config), config)
        state = storage.load()
        changed = state.sync_v2 is None or not protocol.equal(protocol.merge_documents(state.sync_v2, remote), state.sync_v2)
        return RemoteCheckOutcome(remote_changed=changed, remote_hash=content_hash(json.dumps(remote, sort_keys=True).encode()))
    except (WebDavError, ValueError, OSError) as exc:
        return RemoteCheckOutcome(error=str(exc))


def sync_webdav_periodic(storage):
    config = load_webdav_config()
    if not config.enabled or config.sync_interval_minutes <= 0:
        return RemoteCheckOutcome()
    return check_remote_changes(storage, config)
