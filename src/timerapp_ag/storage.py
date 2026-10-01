from __future__ import annotations

import json
import copy
from uuid import uuid4
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .app_info import STORAGE_ORG
from . import platform_paths
from .bitrix_secrets import strip_bitrix_secrets_from_ui
from .domain.merge import merge_states, pick_best_data_file, score_data_file, states_equivalent
from .domain.state import AppState
from .storage_transaction import transaction, atomic_write
from . import sync_protocol as protocol

MAX_BACKUPS = 30
BACKUP_REASON_RE = re.compile(r"[^\w.-]+")


def _qt_data_path_if_exists() -> Path | None:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        return None
    candidate = Path(base) / "data.json"
    return candidate.resolve() if candidate.is_file() else None


def discover_data_files(*, include_qt_fallback: bool = True) -> list[Path]:
    """All known data.json files from current and legacy AppData folders."""
    files: list[Path] = []
    seen: set[Path] = set()
    for root in platform_paths.data_share_roots():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            candidate = (child / "data.json").resolve()
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                files.append(candidate)
    if include_qt_fallback:
        qt_path = _qt_data_path_if_exists()
        if qt_path is not None and qt_path not in seen:
            seen.add(qt_path)
            files.append(qt_path)
    return files


def discover_legacy_data_files() -> list[Path]:
    """Каталоги установок в data_share_roots и пользовательские пути (legacy merge)."""
    files = discover_data_files(include_qt_fallback=False)
    seen = {item.resolve() for item in files}
    from .legacy_merge import extra_legacy_data_files

    for path in extra_legacy_data_files():
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            files.append(resolved)
    return files


def _load_state_from_file(path: Path) -> AppState | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return AppState.from_dict(payload)


def merge_data_files(paths: list[Path]) -> AppState:
    """Merge tasks from every data.json; UI settings come from the richest file."""
    loaded: list[tuple[Path, AppState]] = []
    for path in paths:
        state = _load_state_from_file(path)
        if state is not None:
            loaded.append((path, state))
    if not loaded:
        return AppState()

    loaded.sort(key=lambda item: score_data_file(item[0]), reverse=True)
    merged = merge_states([state for _, state in loaded])
    merged.ui = dict(loaded[0][1].ui)
    return merged


def default_data_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if base:
        path = Path(base)
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return path / "data.json"
        except OSError:
            pass

    fallback = Path.cwd() / ".localdata"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / "data.json"


def stable_data_path() -> Path:
    """Version-independent path: <data_root>/<org>/<APP_TITLE_BASE>/data.json."""
    try:
        return platform_paths.stable_data_path()
    except OSError:
        return default_data_path()


class Storage:
    def __init__(self, path: Path | None = None, *, migrate_legacy: bool = False) -> None:
        self.path = (path or stable_data_path()).resolve()
        self._migrate_legacy = migrate_legacy

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / "backups"

    @property
    def rolling_backup_path(self) -> Path:
        return self.path.parent / f"{self.path.name}.bak"

    def consolidate_legacy_data_files(self) -> AppState:
        """Объединить текущую базу с data.json из других каталогов (по запросу пользователя)."""
        self._consolidate_all_data_files()
        return self.load()

    def _consolidate_all_data_files(self) -> None:
        candidates = list(discover_legacy_data_files())
        if self.path.exists() and self.path.resolve() not in {item.resolve() for item in candidates}:
            candidates.append(self.path)
        if not candidates:
            return

        merged = merge_data_files(candidates)
        current = _load_state_from_file(self.path) if self.path.exists() else AppState()
        if states_equivalent(current, merged):
            return

        if self.path.exists():
            self.create_backup("before-merge")
        if current is not None and current.sync_v2 is not None:
            imported = protocol.import_legacy([t.to_dict() for t in merged.tasks], "migration-" + uuid4().hex)
            self.merge_sync_v2(imported)
        else:
            self.save(merged, update_rolling_backup=False)
        self.create_backup("merge")
        self._archive_legacy_sources(candidates)

    def _archive_legacy_sources(self, sources: list[Path]) -> None:
        archive_root = self.backup_dir / "legacy-sources"
        archive_root.mkdir(parents=True, exist_ok=True)
        primary = self.path.resolve()
        for source in sources:
            if source.resolve() == primary:
                continue
            stamp = datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
            safe_name = BACKUP_REASON_RE.sub("-", source.parent.name).strip("-") or "legacy"
            target = archive_root / f"{safe_name}-{stamp}.json"
            if target.exists():
                continue
            try:
                shutil.copy2(source, target)
            except OSError:
                continue

    def _prune_backups(self) -> None:
        if not self.backup_dir.is_dir():
            return
        backups = sorted(
            self.backup_dir.glob("data-*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for stale in backups[MAX_BACKUPS:]:
            stale.unlink(missing_ok=True)

    def create_backup(self, reason: str = "manual") -> Path | None:
        if not self.path.is_file():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_reason = BACKUP_REASON_RE.sub("-", reason.strip()).strip("-") or "manual"
        destination = self.backup_dir / f"data-{stamp}-{safe_reason}.json"
        shutil.copy2(self.path, destination)
        self._prune_backups()
        return destination

    def _update_rolling_backup(self) -> None:
        if not self.path.is_file():
            return
        shutil.copy2(self.path, self.rolling_backup_path)

    def _load_from_rolling_backup(self) -> AppState | None:
        with transaction(self.path):
            # Another process may have repaired the primary while this reader waited.
            try:
                current = self._raw_state()
                if current.sync_v2 is not None:
                    protocol.validate_document(current.sync_v2)
                current.sync_base_tasks = copy.deepcopy([task.to_dict() for task in current.tasks])
                return current
            except (json.JSONDecodeError, UnicodeError):
                pass
            if not self.rolling_backup_path.is_file():
                return None
            try:
                data = json.loads(self.rolling_backup_path.read_text(encoding="utf-8"))
                state = AppState.from_dict(data)
                if state.sync_v2 is not None:
                    protocol.validate_document(state.sync_v2)
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                return None
            self.create_backup("corrupt-" + uuid4().hex)
            self._commit_state(state, update_rolling_backup=False)
            return state

    def load(self) -> AppState:
        if self._migrate_legacy:
            self._consolidate_all_data_files()
        if not self.path.exists():
            return AppState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeError) as exc:
            restored = self._load_from_rolling_backup()
            if restored is not None:
                return restored
            raise ValueError("Файл данных повреждён; сохраните его и восстановите резервную копию") from exc
        state = AppState.from_dict(data)
        if state.sync_v2 is not None:
            protocol.validate_document(state.sync_v2)
        state.sync_base_tasks = copy.deepcopy([task.to_dict() for task in state.tasks])
        return state

    def _raw_state(self):
        if not self.path.exists():
            return AppState()
        return AppState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def _actor(self, doc):
        # Installation metadata is intentionally outside backups and remote payloads.
        path = self.path.parent / "sync-device.json"
        data = json.loads(path.read_text()) if path.exists() else {"actor": "desktop-" + uuid4().hex, "seq": 0}
        seen = max((o["seq"] for o in doc["ops"] if o["actor"] == data["actor"]), default=0)
        if seen < data["seq"]:
            data = {"actor": "desktop-" + uuid4().hex, "seq": 0}
        return path, data

    def _commit_state(self, state, *, update_rolling_backup=True):
        ui = dict(state.ui)
        strip_bitrix_secrets_from_ui(ui)
        payload = state.to_dict()
        payload["ui"] = ui
        atomic_write(self.path, json.dumps(payload, ensure_ascii=False, indent=2))
        if update_rolling_backup:
            self._update_rolling_backup()
        state.sync_base_tasks = copy.deepcopy([task.to_dict() for task in state.tasks])

    def enable_sync_v2(self):
        with transaction(self.path):
            state = self._raw_state()
            if state.sync_v2 is None:
                self.create_backup("before-sync-v2")
                tasks = [t.to_dict() for t in state.tasks]
                state.sync_v2 = protocol.import_legacy(tasks, "migration-" + uuid4().hex)
                self._commit_state(state)
            else:
                protocol.validate_document(state.sync_v2)
            state.sync_base_tasks = copy.deepcopy([t.to_dict() for t in state.tasks])
            return state

    @staticmethod
    def _project_state(doc, ui):
        from datetime import date
        from .domain.datetime_util import parse_iso_datetime
        tasks = protocol.project_tasks(doc)["tasks"]
        for task in tasks:
            if task.get("status", "open") not in ("open", "running", "paused", "completed"):
                raise ValueError("Некорректный статус задачи в синхронизации")
            if not isinstance(task.get("title"), str) or not task["title"].strip() or not isinstance(task.get("description", ""), str):
                raise ValueError("Некорректные поля задачи в синхронизации")
            date.fromisoformat(task["day"])
            if "created_at" in task:
                parse_iso_datetime(task["created_at"])
            for session in task["sessions"]:
                start = parse_iso_datetime(session["started_at"])
                end = parse_iso_datetime(session["ended_at"]) if session.get("ended_at") is not None else None
                if not isinstance(session.get("comment", ""), str):
                    raise ValueError("Некорректный комментарий сессии")
                if end is not None:
                    a = start if start.tzinfo else start.astimezone()
                    b = end if end.tzinfo else end.astimezone()
                    if b < a:
                        raise ValueError("Окончание сессии раньше начала")
            # Concurrent status/interval registers may disagree. Derive only the
            # local display state; keep the authoritative causal status untouched.
            if any(session.get("ended_at") is None for session in task["sessions"]):
                task["status"] = "running"
            elif task.get("status") == "running":
                task["status"] = "paused"
        return AppState.from_dict({"tasks": tasks, "ui": ui, "sync_v2": doc})

    def merge_sync_v2(self, remote, *, migration_key=None, legacy_tasks=None):
        protocol.validate_document(remote)
        with transaction(self.path):
            state = self._raw_state()
            if state.sync_v2 is None:
                raise ValueError("Сначала включите синхронизацию v2")
            doc = protocol.merge_documents(state.sync_v2, remote)
            if migration_key:
                migrated = list(state.ui.get("sync_v2_remote_imports", []))
                if migration_key not in migrated:
                    if legacy_tasks is not None:
                        self.backup_dir.mkdir(parents=True, exist_ok=True)
                        atomic_write(self.backup_dir / ("remote-legacy-" + migration_key + ".json"), json.dumps({"tasks": legacy_tasks}, ensure_ascii=False))
                    migrated.append(migration_key)
                    state.ui["sync_v2_remote_imports"] = migrated
            result = self._project_state(doc, state.ui)
            self._commit_state(result)
            return result

    def resolve_sync_conflict(self, entity, field, value, *, expected=None):
        with transaction(self.path):
            state = self._raw_state()
            if state.sync_v2 is None:
                raise ValueError("Нет данных синхронизации")
            if expected is not None:
                conflict = next((c for c in protocol.project_document(state.sync_v2)["conflicts"] if c["entity"] == entity and c["field"] == field), None)
                if conflict is None or not protocol.equal(conflict["candidates"], expected):
                    raise ValueError("Конфликт изменился; обновите список вариантов")
            path, actor = self._actor(state.sync_v2)
            doc = protocol.resolve_conflict(state.sync_v2, actor["actor"], entity, field, value)
            actor["seq"] = max((o["seq"] for o in doc["ops"] if o["actor"] == actor["actor"]), default=0)
            atomic_write(path, json.dumps(actor))
            result = self._project_state(doc, state.ui)
            self._commit_state(result)
            return result

    def keep_active_session(self, task_id, session_id, *, expected, now=None):
        """Explicit resolution of concurrent starts; keep all intervals as history."""
        from .models import TaskStatus
        with transaction(self.path):
            state = self._raw_state()
            if state.sync_v2 is None:
                raise ValueError("Нет данных синхронизации")
            active = [(t, session) for t in state.tasks for session in t.sessions if session.ended_at is None]
            actual = sorted([t.id, session.id] for t, session in active)
            if actual != sorted(expected) or [task_id, session_id] not in actual:
                raise ValueError("Список активных сессий изменился; повторите выбор")
            before = [t.to_dict() for t in state.tasks]
            moment = now or datetime.now().astimezone()
            if moment.tzinfo is None:
                moment = moment.astimezone()
            for task, session in active:
                if [task.id, session.id] == [task_id, session_id]:
                    continue
                start = session.start_dt
                if start.tzinfo is None:
                    start = start.astimezone()
                end = max(start, moment)
                session.ended_at = end.isoformat()
                if "duration_seconds" in session.extra:
                    session.extra["duration_seconds"] = int((end - start).total_seconds())
            for task in state.tasks:
                if task.active_session() is not None:
                    task.status = TaskStatus.RUNNING
                elif task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.PAUSED
            path, actor = self._actor(state.sync_v2)
            state.sync_v2 = protocol.reconcile_tasks(state.sync_v2, before, [t.to_dict() for t in state.tasks], actor["actor"])
            actor["seq"] = max((o["seq"] for o in state.sync_v2["ops"] if o["actor"] == actor["actor"]), default=0)
            atomic_write(path, json.dumps(actor))
            self._commit_state(state)
            return state

    def save(self, state: AppState, *, update_rolling_backup: bool = True) -> None:
        with transaction(self.path):
            current = self._raw_state()
            if current.sync_v2 is not None:
                before = state.sync_base_tasks
                if before is None:
                    raise ValueError("Устаревшая копия без исходной версии; перечитайте данные перед сохранением")
                base = state.sync_v2
                if base is None:
                    # UI loaded before migration: independent ancestry must not overwrite tombstones.
                    base = protocol.import_legacy(before, "migration-" + uuid4().hex)
                path, actor = self._actor(current.sync_v2)
                edit_actor = actor["actor"] if protocol.equal(base, current.sync_v2) else "branch-" + uuid4().hex
                edited = protocol.reconcile_tasks(base, before, [t.to_dict() for t in state.tasks], edit_actor)
                doc = protocol.merge_documents(current.sync_v2, edited)
                actor["seq"] = max((o["seq"] for o in doc["ops"] if o["actor"] == actor["actor"]), default=0)
                atomic_write(path, json.dumps(actor))
                merged = self._project_state(doc, state.ui)
                state.tasks, state.sync_v2 = merged.tasks, doc
                if "sync_v2_remote_imports" in current.ui:
                    state.ui["sync_v2_remote_imports"] = current.ui["sync_v2_remote_imports"]
            self._commit_state(state, update_rolling_backup=update_rolling_backup)


# Backward-compatible re-exports
__all__ = [
    "AppState",
    "Storage",
    "discover_data_files",
    "discover_legacy_data_files",
    "merge_data_files",
    "pick_best_data_file",
    "stable_data_path",
]
