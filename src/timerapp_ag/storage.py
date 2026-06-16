from __future__ import annotations

import json
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
    """Каталоги установок в data_share_roots без Qt AppDataLocation (для legacy merge)."""
    return discover_data_files(include_qt_fallback=False)


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
        if not self.rolling_backup_path.is_file():
            return None
        try:
            data = json.loads(self.rolling_backup_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        state = AppState.from_dict(data)
        self.save(state, update_rolling_backup=False)
        return state

    def load(self) -> AppState:
        if self._migrate_legacy:
            self._consolidate_all_data_files()
        if not self.path.exists():
            return AppState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            restored = self._load_from_rolling_backup()
            if restored is not None:
                return restored
            return AppState()
        return AppState.from_dict(data)

    def save(self, state: AppState, *, update_rolling_backup: bool = True) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ui = dict(state.ui)
        strip_bitrix_secrets_from_ui(ui)
        payload = json.dumps(
            {"tasks": [task.to_dict() for task in state.tasks], "ui": ui},
            ensure_ascii=False,
            indent=2,
        )
        temp_path = self.path.with_suffix(".json.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        os.replace(temp_path, self.path)
        if update_rolling_backup:
            self._update_rolling_backup()


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
