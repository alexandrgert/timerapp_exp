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
from .webdav_sync_log import append_entry, count_tasks_in_payload

logger = logging.getLogger(__name__)


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


def _remote_changed_since_sync(
    config: WebDavConfig,
    remote_hash: str,
    local_hash: str,
) -> bool:
    """Удалённый файл изменился с прошлой синхронизации или отличается от локального."""
    if config.last_remote_content_hash:
        return remote_hash != config.last_remote_content_hash
    return bool(local_hash) and remote_hash != local_hash


def _log_sync_outcome(
    op: str,
    outcome: SyncOutcome,
    *,
    uploaded_tasks: int | None = None,
    downloaded_tasks: int | None = None,
) -> SyncOutcome:
    uploaded = outcome.uploaded_tasks if uploaded_tasks is None else uploaded_tasks
    downloaded = outcome.downloaded_tasks if downloaded_tasks is None else downloaded_tasks
    outcome.uploaded_tasks = uploaded
    outcome.downloaded_tasks = downloaded
    if not outcome.error and uploaded == 0 and downloaded == 0 and not outcome.notice and outcome.state is None:
        # no-op sync (disabled) — не засоряем журнал
        if op in {"startup", "shutdown", "periodic"}:
            return outcome
    append_entry(
        op,
        uploaded_tasks=uploaded,
        downloaded_tasks=downloaded,
        ok=not bool(outcome.error),
        error=outcome.error,
    )
    return outcome


def pull_and_merge(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
    log_op: str = "pull",
) -> SyncOutcome:
    """Скачать удалённую базу и объединить с локальной."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        raise WebDavError("Синхронизация WebDAV отключена")

    try:
        client = WebDavClient(config)
        conflict_detected = False
        candidates = [storage.path]
        downloaded_tasks = 0

        if client.exists():
            remote_payload = client.download()
            downloaded_tasks = count_tasks_in_payload(remote_payload)
            remote_meta = _read_remote_meta(client, config)
            remote_hash = _remote_payload_hash(remote_payload, remote_meta)
            local_hash = content_hash(storage.path.read_bytes()) if storage.path.is_file() else ""
            if _remote_changed_since_sync(config, remote_hash, local_hash):
                conflict_detected = True
                logger.warning(
                    "WebDAV conflict: remote hash changed (%s -> %s)",
                    (config.last_remote_content_hash or local_hash)[:12],
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

        return _log_sync_outcome(
            log_op,
            SyncOutcome(
                state=merged,
                conflict_detected=conflict_detected,
                notice=notice,
                downloaded_tasks=downloaded_tasks,
            ),
        )
    except WebDavError as exc:
        _log_sync_outcome(log_op, SyncOutcome(error=str(exc)))
        raise


def push_local(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
    log_op: str = "push",
) -> SyncOutcome:
    """Pull-before-push: merge с сервером, затем upload data.json + sync-meta."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        raise WebDavError("Синхронизация WebDAV отключена")
    if not storage.path.is_file():
        raise WebDavError("Локальный файл данных не найден")

    try:
        client = WebDavClient(config)
        conflict_detected = False
        downloaded_tasks = 0

        if client.exists():
            remote_payload = client.download()
            downloaded_tasks = count_tasks_in_payload(remote_payload)
            remote_meta = _read_remote_meta(client, config)
            remote_hash = _remote_payload_hash(remote_payload, remote_meta)
            local_hash = content_hash(storage.path.read_bytes())
            if _remote_changed_since_sync(config, remote_hash, local_hash):
                conflict_detected = True
                logger.warning("WebDAV push: remote changed since last sync, merging before upload")
            merged = _merge_local_with_remote(storage, remote_payload)
            _finalize_merged_state(storage, merged, reason="webdav-push-merge")
        else:
            merged = AppState.from_dict(json.loads(storage.path.read_text(encoding="utf-8")))
            normalize_running_tasks(merged)
            storage.save(merged, update_rolling_backup=False)

        payload = storage.path.read_bytes()
        uploaded_tasks = count_tasks_in_payload(payload)
        meta = _upload_payload(client, config, payload)
        mark_webdav_sync_ok(config, remote_hash=meta.content_hash, had_conflict=conflict_detected)

        notice = ""
        if conflict_detected:
            notice = "Перед загрузкой выполнено слияние с более новой версией на сервере."

        return _log_sync_outcome(
            log_op,
            SyncOutcome(
                state=merged,
                conflict_detected=conflict_detected,
                notice=notice,
                uploaded_tasks=uploaded_tasks,
                downloaded_tasks=downloaded_tasks,
            ),
        )
    except WebDavError as exc:
        _log_sync_outcome(log_op, SyncOutcome(error=str(exc)))
        raise


def push_merged_state(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
    log_op: str | None = None,
) -> SyncOutcome:
    """Загрузить текущий локальный data.json без повторного скачивания с сервера."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        raise WebDavError("Синхронизация WebDAV отключена")
    if not storage.path.is_file():
        raise WebDavError("Локальный файл данных не найден")

    try:
        merged = AppState.from_dict(json.loads(storage.path.read_text(encoding="utf-8")))
        normalize_running_tasks(merged)
        storage.save(merged, update_rolling_backup=False)

        payload = storage.path.read_bytes()
        uploaded_tasks = count_tasks_in_payload(payload)
        client = WebDavClient(config)
        meta = _upload_payload(client, config, payload)
        mark_webdav_sync_ok(config, remote_hash=meta.content_hash, had_conflict=False)
        outcome = SyncOutcome(state=merged, uploaded_tasks=uploaded_tasks)
        if log_op:
            return _log_sync_outcome(log_op, outcome)
        return outcome
    except WebDavError as exc:
        if log_op:
            _log_sync_outcome(log_op, SyncOutcome(error=str(exc)))
        raise


def push_local_upload_only(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
    log_op: str = "push_upload_only",
) -> SyncOutcome:
    """Отправить локальный data.json без слияния с сервером (опция при выходе)."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        raise WebDavError("Синхронизация WebDAV отключена")
    if not storage.path.is_file():
        raise WebDavError("Локальный файл данных не найден")

    try:
        client = WebDavClient(config)
        conflict_detected = False
        local_payload = storage.path.read_bytes()
        local_hash = content_hash(local_payload)
        downloaded_tasks = 0

        if client.exists():
            remote_payload = client.download()
            downloaded_tasks = count_tasks_in_payload(remote_payload)
            remote_meta = _read_remote_meta(client, config)
            remote_hash = _remote_payload_hash(remote_payload, remote_meta)
            if _remote_changed_since_sync(config, remote_hash, local_hash):
                conflict_detected = True
                logger.warning(
                    "WebDAV upload-only: remote changed since last sync (%s -> %s)",
                    (config.last_remote_content_hash or local_hash)[:12],
                    remote_hash[:12],
                )

        payload = local_payload
        uploaded_tasks = count_tasks_in_payload(payload)
        meta = _upload_payload(client, config, payload)
        mark_webdav_sync_ok(config, remote_hash=meta.content_hash, had_conflict=conflict_detected)

        notice = ""
        if conflict_detected:
            notice = (
                "При выходе на сервер отправлена локальная копия без слияния; "
                "в облаке была более новая версия."
            )

        return _log_sync_outcome(
            log_op,
            SyncOutcome(
                conflict_detected=conflict_detected,
                notice=notice,
                uploaded_tasks=uploaded_tasks,
                downloaded_tasks=downloaded_tasks,
            ),
        )
    except WebDavError as exc:
        _log_sync_outcome(log_op, SyncOutcome(error=str(exc)))
        raise


def _persist_shutdown_notice(outcome: SyncOutcome) -> None:
    if outcome.notice and outcome.conflict_detected:
        save_webdav_pending_notice(outcome.notice)


def sync_webdav_on_shutdown(storage: Storage) -> SyncOutcome:
    config = load_webdav_config()
    if not config.enabled or not config.sync_on_shutdown:
        return SyncOutcome()
    try:
        if config.shutdown_upload_only:
            outcome = push_local_upload_only(
                storage, config, require_enabled=True, log_op="shutdown"
            )
        else:
            outcome = push_local(storage, config, require_enabled=True, log_op="shutdown")
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
        return pull_and_merge(storage, config, require_enabled=True, log_op="startup")
    except WebDavError as exc:
        logger.error("WebDAV startup sync failed: %s", exc)
        mark_webdav_sync_error(config, str(exc))
        return SyncOutcome(error=str(exc))


def save_webdav_settings(config: WebDavConfig) -> None:
    save_webdav_config(config)


def sync_webdav_now(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = False,
) -> SyncOutcome:
    """Скачать, объединить и загрузить обратно (ручная / периодическая синхронизация)."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        return SyncOutcome(error="Синхронизация WebDAV отключена")
    if not config.is_configured():
        return SyncOutcome(error="WebDAV не настроен: укажите URL и имя пользователя")
    try:
        pull_outcome = pull_and_merge(storage, config, require_enabled=False, log_op="sync_pull")
        push_outcome = push_merged_state(storage, config, require_enabled=False, log_op="sync_push")
        notices = [part for part in (pull_outcome.notice, push_outcome.notice) if part]
        notice = " ".join(notices) if notices else "Синхронизация завершена"
        return SyncOutcome(
            state=push_outcome.state or pull_outcome.state,
            conflict_detected=pull_outcome.conflict_detected or push_outcome.conflict_detected,
            notice=notice,
            uploaded_tasks=push_outcome.uploaded_tasks,
            downloaded_tasks=pull_outcome.downloaded_tasks,
        )
    except WebDavError as exc:
        logger.error("WebDAV sync now failed: %s", exc)
        mark_webdav_sync_error(config, str(exc))
        return SyncOutcome(error=str(exc))


def sync_webdav_on_reconnect(storage: Storage) -> SyncOutcome:
    """Push после восстановления сети (если WebDAV включён и настроен)."""
    config = load_webdav_config()
    if not config.enabled or not config.is_configured():
        return SyncOutcome()
    try:
        return push_local(storage, config, require_enabled=True, log_op="reconnect_push")
    except WebDavError as exc:
        logger.error("WebDAV reconnect push failed: %s", exc)
        mark_webdav_sync_error(config, str(exc))
        return SyncOutcome(error=str(exc))


def check_remote_changes(
    storage: Storage,
    config: WebDavConfig | None = None,
    *,
    require_enabled: bool = True,
) -> RemoteCheckOutcome:
    """Проверить, изменился ли удалённый data.json с момента последней синхронизации."""
    config = config or load_webdav_config()
    if require_enabled and not config.enabled:
        return RemoteCheckOutcome()
    if not config.is_configured():
        return RemoteCheckOutcome(error="WebDAV не настроен: укажите URL и имя пользователя")
    try:
        client = WebDavClient(config)
        if not client.exists():
            return RemoteCheckOutcome()
        remote_payload = client.download()
        remote_meta = _read_remote_meta(client, config)
        remote_hash = _remote_payload_hash(remote_payload, remote_meta)
        local_hash = content_hash(storage.path.read_bytes()) if storage.path.is_file() else ""
        changed = _remote_changed_since_sync(config, remote_hash, local_hash)
        return RemoteCheckOutcome(remote_changed=changed, remote_hash=remote_hash)
    except WebDavError as exc:
        logger.warning("WebDAV remote check failed: %s", exc)
        return RemoteCheckOutcome(error=str(exc))


def sync_webdav_periodic(storage: Storage) -> RemoteCheckOutcome:
    config = load_webdav_config()
    if not config.enabled or config.sync_interval_minutes <= 0:
        return RemoteCheckOutcome()
    return check_remote_changes(storage, config, require_enabled=True)
