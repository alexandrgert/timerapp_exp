"""Синхронизация data.json с WebDAV: merge, versioning, pull-before-push."""
from __future__ import annotations

import json
import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .domain.sync_normalize import normalize_running_tasks
from .storage import AppState, Storage, merge_data_files
from .webdav_client import WebDavClient, WebDavError
from .webdav_config import (
    WebDavConfig,
    load_webdav_config,
    mark_webdav_sync_error,
    mark_webdav_sync_ok,
    save_webdav_config,
    save_webdav_pending_notice,
)
from .webdav_meta import RemoteSyncMeta, content_hash, meta_to_bytes, new_meta, parse_meta_bytes

logger = logging.getLogger(__name__)


@dataclass
class SyncOutcome:
    state: AppState | None = None
    error: str = ""
    conflict_detected: bool = False
    notice: str = ""


def _read_remote_meta(client: WebDavClient, config: WebDavConfig) -> RemoteSyncMeta | None:
    meta_url = config.meta_remote_url()
    if not client.exists(meta_url):
        return None
    try:
        payload = client.download(meta_url)
    except WebDavError as exc:
        if exc.status_code == 404:
            return None
        raise
    return parse_meta_bytes(payload)


_META_UPLOAD_ATTEMPTS = 3
_FULL_UPLOAD_CYCLES = 2


def _remote_payload_hash(payload: bytes, meta: RemoteSyncMeta | None) -> str:
    """SHA-256 содержимого; при рассинхроне meta и файла — доверяем файлу."""
    file_hash = content_hash(payload)
    if meta is None:
        return file_hash
    if meta.content_hash != file_hash:
        logger.warning(
            "WebDAV sync-meta hash mismatch (meta=%s, file=%s); using file hash",
            meta.content_hash[:12],
            file_hash[:12],
        )
        return file_hash
    return meta.content_hash


def _upload_meta_with_retries(
    client: WebDavClient,
    meta_url: str,
    meta_bytes: bytes,
) -> None:
    last_error: WebDavError | None = None
    for attempt in range(1, _META_UPLOAD_ATTEMPTS + 1):
        try:
            client.upload(meta_url, meta_bytes)
            return
        except WebDavError as exc:
            last_error = exc
            logger.warning(
                "WebDAV sync-meta upload attempt %s/%s failed: %s",
                attempt,
                _META_UPLOAD_ATTEMPTS,
                exc,
            )
            if attempt < _META_UPLOAD_ATTEMPTS:
                time.sleep(0.5 * attempt)
    assert last_error is not None
    raise last_error


def _upload_payload(client: WebDavClient, config: WebDavConfig, payload: bytes) -> RemoteSyncMeta:
    data_url = config.remote_url()
    meta_url = config.meta_remote_url()
    device_id = config.ensure_device_id()
    meta = new_meta(payload, device_id)
    meta_bytes = meta_to_bytes(meta)
    last_error: WebDavError | None = None
    for cycle in range(1, _FULL_UPLOAD_CYCLES + 1):
        try:
            client.upload(data_url, payload)
            _upload_meta_with_retries(client, meta_url, meta_bytes)
            return meta
        except WebDavError as exc:
            last_error = exc
            logger.warning(
                "WebDAV upload cycle %s/%s failed: %s",
                cycle,
                _FULL_UPLOAD_CYCLES,
                exc,
            )
            if cycle < _FULL_UPLOAD_CYCLES:
                time.sleep(0.5 * cycle)
    assert last_error is not None
    raise WebDavError(
        f"Не удалось загрузить data.json и sync-meta после {_FULL_UPLOAD_CYCLES} циклов: {last_error}"
    ) from last_error


def _merge_local_with_remote(storage: Storage, remote_payload: bytes) -> AppState:
    try:
        json.loads(remote_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebDavError("Удалённый файл не является корректным JSON") from exc

    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as handle:
        handle.write(remote_payload)
        remote_path = Path(handle.name)
    try:
        candidates = [storage.path, remote_path]
        return merge_data_files(candidates)
    finally:
        remote_path.unlink(missing_ok=True)


def _finalize_merged_state(storage: Storage, merged: AppState, *, reason: str) -> AppState:
    normalize_running_tasks(merged)
    storage.save(merged, update_rolling_backup=False)
    storage.create_backup(reason)
    return merged


def pull_and_merge(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
) -> SyncOutcome:
    """Скачать удалённую базу и объединить с локальной."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        raise WebDavError("Синхронизация WebDAV отключена")

    client = WebDavClient(config)
    conflict_detected = False
    candidates = [storage.path]

    if client.exists():
        remote_payload = client.download()
        remote_meta = _read_remote_meta(client, config)
        remote_hash = _remote_payload_hash(remote_payload, remote_meta)
        if (
            config.last_remote_content_hash
            and remote_hash != config.last_remote_content_hash
        ):
            conflict_detected = True
            logger.warning(
                "WebDAV conflict: remote hash changed (%s -> %s)",
                config.last_remote_content_hash[:12],
                remote_hash[:12],
            )
        merged = _merge_local_with_remote(storage, remote_payload)
    else:
        merged = merge_data_files(candidates) if storage.path.exists() else AppState()

    merged = _finalize_merged_state(storage, merged, reason="webdav-pull")
    remote_hash = content_hash(storage.path.read_bytes())
    mark_webdav_sync_ok(config, remote_hash=remote_hash, had_conflict=conflict_detected)

    notice = ""
    if conflict_detected:
        notice = "Обнаружен конфликт версий: данные объединены с сервера."

    return SyncOutcome(state=merged, conflict_detected=conflict_detected, notice=notice)


def push_local(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
) -> SyncOutcome:
    """Pull-before-push: merge с сервером, затем upload data.json + sync-meta."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        raise WebDavError("Синхронизация WebDAV отключена")
    if not storage.path.is_file():
        raise WebDavError("Локальный файл данных не найден")

    client = WebDavClient(config)
    conflict_detected = False

    if client.exists():
        remote_payload = client.download()
        remote_meta = _read_remote_meta(client, config)
        remote_hash = _remote_payload_hash(remote_payload, remote_meta)
        if (
            config.last_remote_content_hash
            and remote_hash != config.last_remote_content_hash
        ):
            conflict_detected = True
            logger.warning("WebDAV push: remote changed since last sync, merging before upload")
        merged = _merge_local_with_remote(storage, remote_payload)
        _finalize_merged_state(storage, merged, reason="webdav-push-merge")
    else:
        merged = AppState.from_dict(json.loads(storage.path.read_text(encoding="utf-8")))
        normalize_running_tasks(merged)
        storage.save(merged, update_rolling_backup=False)

    payload = storage.path.read_bytes()
    meta = _upload_payload(client, config, payload)
    mark_webdav_sync_ok(config, remote_hash=meta.content_hash, had_conflict=conflict_detected)

    notice = ""
    if conflict_detected:
        notice = "Перед загрузкой выполнено слияние с более новой версией на сервере."

    return SyncOutcome(state=merged, conflict_detected=conflict_detected, notice=notice)


def push_local_upload_only(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
) -> SyncOutcome:
    """Отправить локальный data.json без слияния с сервером (опция при выходе)."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        raise WebDavError("Синхронизация WebDAV отключена")
    if not storage.path.is_file():
        raise WebDavError("Локальный файл данных не найден")

    client = WebDavClient(config)
    conflict_detected = False

    if client.exists():
        remote_payload = client.download()
        remote_meta = _read_remote_meta(client, config)
        remote_hash = _remote_payload_hash(remote_payload, remote_meta)
        if (
            config.last_remote_content_hash
            and remote_hash != config.last_remote_content_hash
        ):
            conflict_detected = True
            logger.warning(
                "WebDAV upload-only: remote changed since last sync (%s -> %s)",
                config.last_remote_content_hash[:12],
                remote_hash[:12],
            )

    payload = storage.path.read_bytes()
    meta = _upload_payload(client, config, payload)
    mark_webdav_sync_ok(config, remote_hash=meta.content_hash, had_conflict=conflict_detected)

    notice = ""
    if conflict_detected:
        notice = (
            "При выходе на сервер отправлена локальная копия без слияния; "
            "в облаке была более новая версия."
        )

    return SyncOutcome(conflict_detected=conflict_detected, notice=notice)


def _persist_shutdown_notice(outcome: SyncOutcome) -> None:
    if outcome.notice and outcome.conflict_detected:
        save_webdav_pending_notice(outcome.notice)


def sync_webdav_on_shutdown(storage: Storage) -> SyncOutcome:
    config = load_webdav_config()
    if not config.enabled or not config.sync_on_shutdown:
        return SyncOutcome()
    try:
        if config.shutdown_upload_only:
            outcome = push_local_upload_only(storage, config, require_enabled=True)
        else:
            outcome = push_local(storage, config, require_enabled=True)
        _persist_shutdown_notice(outcome)
        return outcome
    except WebDavError as exc:
        logger.error("WebDAV shutdown sync failed: %s", exc)
        mark_webdav_sync_error(config, str(exc))
        return SyncOutcome(error=str(exc))


def test_webdav_connection(config: WebDavConfig) -> str:
    client = WebDavClient(config)
    if client.exists():
        return client.test_connection() + " (удалённый файл найден)"
    client._ensure_collection(config.remote_url())
    return "Подключение успешно (удалённый файл будет создан при первой синхронизации)"


def sync_webdav_on_startup(storage: Storage) -> SyncOutcome:
    config = load_webdav_config()
    if not config.enabled or not config.sync_on_startup:
        return SyncOutcome()
    try:
        return pull_and_merge(storage, config, require_enabled=True)
    except WebDavError as exc:
        logger.error("WebDAV startup sync failed: %s", exc)
        mark_webdav_sync_error(config, str(exc))
        return SyncOutcome(error=str(exc))


def save_webdav_settings(config: WebDavConfig) -> None:
    save_webdav_config(config)
