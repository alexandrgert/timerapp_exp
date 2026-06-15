"""Обнаружение и опциональное слияние баз data.json от старых версий / каталогов."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import platform_paths
from .domain.merge import states_equivalent
from .domain.state import AppState
from .secure_files import write_json_secrets
from .storage import discover_data_files, merge_data_files


@dataclass(frozen=True)
class LegacyMergePreview:
    primary_path: Path
    source_paths: list[Path]
    current_tasks: int
    merged_tasks: int
    new_titles: list[str]
    source_labels: list[str]


def _legacy_merge_config_path() -> Path:
    return platform_paths.config_dir() / "legacy-merge.json"


def _load_state(path: Path) -> AppState:
    if not path.is_file():
        return AppState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppState()
    return AppState.from_dict(payload)


def sources_fingerprint(paths: list[Path]) -> str:
    parts = sorted(
        f"{item.resolve()}:{item.stat().st_mtime_ns}"
        for item in paths
        if item.is_file()
    )
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:24]


def load_declined_fingerprint() -> str:
    path = _legacy_merge_config_path()
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("declined_fingerprint") or "").strip()


def save_declined_fingerprint(fingerprint: str) -> None:
    write_json_secrets(
        _legacy_merge_config_path(),
        {"declined_fingerprint": fingerprint.strip()},
    )


def clear_declined_fingerprint() -> None:
    save_declined_fingerprint("")


def _source_label(path: Path) -> str:
    return path.parent.name or path.name


def find_legacy_merge_preview(primary: Path) -> LegacyMergePreview | None:
    """Если есть другие data.json, merge которых изменит текущую базу — вернуть preview."""
    primary = primary.resolve()
    candidates = discover_data_files()
    if primary.is_file() and primary not in {item.resolve() for item in candidates}:
        candidates.append(primary)

    others = [path for path in candidates if path.resolve() != primary]
    if not others:
        return None

    merge_paths = ([primary] if primary.is_file() else []) + others
    current = _load_state(primary)
    merged = merge_data_files(merge_paths)
    if states_equivalent(current, merged):
        return None

    current_ids = {task.id for task in current.tasks}
    new_titles = [task.title for task in merged.tasks if task.id not in current_ids][:5]
    return LegacyMergePreview(
        primary_path=primary,
        source_paths=others,
        current_tasks=len(current.tasks),
        merged_tasks=len(merged.tasks),
        new_titles=new_titles,
        source_labels=[_source_label(path) for path in others],
    )


def should_prompt_on_startup(preview: LegacyMergePreview) -> bool:
    fingerprint = sources_fingerprint(preview.source_paths)
    return fingerprint != load_declined_fingerprint()


def mark_legacy_merge_declined(preview: LegacyMergePreview) -> None:
    save_declined_fingerprint(sources_fingerprint(preview.source_paths))


def format_legacy_merge_message(preview: LegacyMergePreview) -> str:
    lines = [
        "Найдены базы задач от прежних версий или других каталогов установки.",
        "",
        f"Сейчас задач: {preview.current_tasks}",
        f"После объединения: {preview.merged_tasks}",
    ]
    if preview.source_labels:
        lines.extend(["", "Источники:"])
        lines.extend(f"• {label}" for label in preview.source_labels[:5])
    if preview.new_titles:
        lines.extend(["", "Примеры задач, которые будут добавлены:"])
        lines.extend(f"• {title}" for title in preview.new_titles)
    lines.extend(["", "Объединить данные сейчас?"])
    return "\n".join(lines)
