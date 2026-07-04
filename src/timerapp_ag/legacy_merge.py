"""Обнаружение и опциональное слияние баз data.json от старых версий / каталогов."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import platform_paths
from .domain.merge import states_equivalent
from .domain.state import AppState
from .secure_files import write_json_secrets
from .storage import discover_legacy_data_files, merge_data_files


@dataclass(frozen=True)
class LegacyMergePreview:
    primary_path: Path
    source_paths: list[Path]
    current_tasks: int
    merged_tasks: int
    new_tasks_count: int
    enriched_tasks_count: int
    extra_sessions_count: int
    new_titles: list[str]
    enriched_titles: list[str]
    source_labels: list[str]
    ui_diff_lines: list[str]


def _legacy_merge_config_path() -> Path:
    return platform_paths.config_dir() / "legacy-merge.json"


def load_legacy_merge_config() -> dict[str, Any]:
    path = _legacy_merge_config_path()
    if not path.is_file():
        return {"declined_fingerprint": "", "extra_data_paths": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"declined_fingerprint": "", "extra_data_paths": []}
    if not isinstance(payload, dict):
        return {"declined_fingerprint": "", "extra_data_paths": []}
    extra = payload.get("extra_data_paths")
    if not isinstance(extra, list):
        extra = []
    return {
        "declined_fingerprint": str(payload.get("declined_fingerprint") or "").strip(),
        "extra_data_paths": [str(item).strip() for item in extra if str(item).strip()],
    }


def save_legacy_merge_config(config: dict[str, Any]) -> None:
    write_json_secrets(
        _legacy_merge_config_path(),
        {
            "declined_fingerprint": str(config.get("declined_fingerprint") or "").strip(),
            "extra_data_paths": [
                str(item).strip()
                for item in (config.get("extra_data_paths") or [])
                if str(item).strip()
            ],
        },
    )


def resolve_legacy_data_json_path(raw: str | Path) -> Path | None:
    """Каталог с data.json или сам файл data.json."""
    path = Path(raw).expanduser()
    try:
        path = path.resolve()
    except OSError:
        return None
    if path.is_file():
        return path if path.name == "data.json" else None
    if path.is_dir():
        candidate = path / "data.json"
        return candidate.resolve() if candidate.is_file() else None
    return None


def list_configured_legacy_locations() -> list[str]:
    return list(load_legacy_merge_config()["extra_data_paths"])


def extra_legacy_data_files() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for raw in list_configured_legacy_locations():
        resolved = resolve_legacy_data_json_path(raw)
        if resolved is not None and resolved not in seen:
            seen.add(resolved)
            files.append(resolved)
    return files


def add_configured_legacy_location(raw: str | Path) -> tuple[Path | None, str]:
    resolved = resolve_legacy_data_json_path(raw)
    if resolved is None:
        return None, "Не найден data.json в указанном каталоге или файле."
    storage_key = str(resolved.parent)
    config = load_legacy_merge_config()
    locations = list(config["extra_data_paths"])
    if storage_key not in locations:
        locations.append(storage_key)
    config["extra_data_paths"] = locations
    save_legacy_merge_config(config)
    return resolved, ""


def remove_configured_legacy_location(raw: str | Path) -> bool:
    resolved = resolve_legacy_data_json_path(raw)
    if resolved is None:
        target = str(Path(raw).expanduser()).strip()
    else:
        target = str(resolved.parent)
    config = load_legacy_merge_config()
    locations = [item for item in config["extra_data_paths"] if item != target]
    if len(locations) == len(config["extra_data_paths"]):
        return False
    config["extra_data_paths"] = locations
    save_legacy_merge_config(config)
    return True


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
    return str(load_legacy_merge_config()["declined_fingerprint"])


def save_declined_fingerprint(fingerprint: str) -> None:
    config = load_legacy_merge_config()
    config["declined_fingerprint"] = fingerprint.strip()
    save_legacy_merge_config(config)


def clear_declined_fingerprint() -> None:
    save_declined_fingerprint("")


def _source_label(path: Path) -> str:
    parent = path.parent.resolve()
    for item in list_configured_legacy_locations():
        resolved = resolve_legacy_data_json_path(item)
        if resolved is not None and resolved.parent.resolve() == parent:
            return str(parent)
    return parent.name or path.name


def _merge_stats(current: AppState, merged: AppState) -> tuple[int, int, int, list[str], list[str]]:
    current_by_id = {task.id: task for task in current.tasks}
    new_titles: list[str] = []
    enriched_titles: list[str] = []
    extra_sessions = 0

    for task in merged.tasks:
        existing = current_by_id.get(task.id)
        if existing is None:
            new_titles.append(task.title)
            continue
        added_sessions = len(task.sessions) - len(existing.sessions)
        if added_sessions > 0 or task.title != existing.title:
            enriched_titles.append(task.title)
            if added_sessions > 0:
                extra_sessions += added_sessions

    return len(new_titles), len(enriched_titles), extra_sessions, new_titles, enriched_titles


def _ui_diff_lines(current: AppState, merged: AppState) -> list[str]:
    labels = {
        "schema_version": "Версия схемы",
        "plan_rollover_day": "День rollover плана",
        "filter_open_only": "Фильтр только открытых",
        "reminder_interval_minutes": "Интервал напоминания (мин)",
    }
    lines: list[str] = []
    for key, label in labels.items():
        if current.ui.get(key) != merged.ui.get(key):
            lines.append(f"{label}: {current.ui.get(key)!r} → {merged.ui.get(key)!r}")

    current_focus = current.ui.get("focus_timer")
    merged_focus = merged.ui.get("focus_timer")
    if isinstance(current_focus, dict) and isinstance(merged_focus, dict):
        for key, label in (
            ("selected_minutes", "Фокус: выбранные минуты"),
            ("duration_minutes", "Фокус: длительность"),
            ("ends_at", "Фокус: окончание"),
            ("session_task_id", "Фокус: задача сессии"),
            ("paused_task_id", "Фокус: задача на паузе"),
        ):
            if current_focus.get(key) != merged_focus.get(key):
                lines.append(f"{label}: {current_focus.get(key)!r} → {merged_focus.get(key)!r}")
    elif current_focus != merged_focus:
        lines.append("Настройки фокус-таймера будут обновлены")

    portal_current = (current.ui.get("bitrix") or {}).get("portal") if isinstance(current.ui.get("bitrix"), dict) else None
    portal_merged = (merged.ui.get("bitrix") or {}).get("portal") if isinstance(merged.ui.get("bitrix"), dict) else None
    if portal_current != portal_merged:
        lines.append("Настройки портала Битрикс24 (ui.bitrix.portal) будут взяты из более полной базы")

    return lines


def find_legacy_merge_preview(primary: Path) -> LegacyMergePreview | None:
    """Если есть другие data.json, merge которых изменит текущую базу — вернуть preview."""
    primary = primary.resolve()
    candidates = discover_legacy_data_files()
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

    new_count, enriched_count, extra_sessions, new_titles, enriched_titles = _merge_stats(current, merged)
    return LegacyMergePreview(
        primary_path=primary,
        source_paths=others,
        current_tasks=len(current.tasks),
        merged_tasks=len(merged.tasks),
        new_tasks_count=new_count,
        enriched_tasks_count=enriched_count,
        extra_sessions_count=extra_sessions,
        new_titles=new_titles[:5],
        enriched_titles=enriched_titles[:5],
        source_labels=[_source_label(path) for path in others],
        ui_diff_lines=_ui_diff_lines(current, merged),
    )


def should_prompt_on_startup(preview: LegacyMergePreview) -> bool:
    fingerprint = sources_fingerprint(preview.source_paths)
    return fingerprint != load_declined_fingerprint()


def mark_legacy_merge_declined(preview: LegacyMergePreview) -> None:
    save_declined_fingerprint(sources_fingerprint(preview.source_paths))


def format_legacy_merge_summary(preview: LegacyMergePreview) -> str:
    lines = [
        "Найдены базы задач от прежних версий или других каталогов установки.",
        "",
        f"Сейчас задач: {preview.current_tasks}",
        f"После объединения: {preview.merged_tasks}",
    ]
    change_parts: list[str] = []
    if preview.new_tasks_count:
        change_parts.append(f"+{preview.new_tasks_count} новых задач")
    if preview.extra_sessions_count:
        change_parts.append(f"+{preview.extra_sessions_count} сессий у существующих задач")
    elif preview.enriched_tasks_count:
        change_parts.append(f"обновятся данные у {preview.enriched_tasks_count} задач")
    if change_parts:
        lines.append("Изменения: " + ", ".join(change_parts) + ".")
    lines.extend(["", "Объединить данные сейчас?", "", "Нажмите «Показать подробности…» для полного списка."])
    return "\n".join(lines)


def format_legacy_merge_details(preview: LegacyMergePreview) -> str:
    lines: list[str] = []
    if preview.source_labels:
        lines.append("Источники:")
        lines.extend(f"• {label}" for label in preview.source_labels)
    if preview.new_titles:
        lines.extend(["", "Новые задачи (примеры):"])
        lines.extend(f"• {title}" for title in preview.new_titles)
        if preview.new_tasks_count > len(preview.new_titles):
            lines.append(f"… и ещё {preview.new_tasks_count - len(preview.new_titles)}")
    if preview.enriched_titles:
        lines.extend(["", "Обновятся существующие задачи (примеры):"])
        lines.extend(f"• {title}" for title in preview.enriched_titles)
        if preview.enriched_tasks_count > len(preview.enriched_titles):
            lines.append(f"… и ещё {preview.enriched_tasks_count - len(preview.enriched_titles)}")
    if preview.ui_diff_lines:
        lines.extend(["", "Настройки интерфейса (ui):"])
        lines.extend(f"• {item}" for item in preview.ui_diff_lines)
    if not lines:
        return "Дополнительных сведений нет."
    return "\n".join(lines)


def format_legacy_merge_message(preview: LegacyMergePreview) -> str:
    """Полный текст (summary + details) для обратной совместимости."""
    summary = format_legacy_merge_summary(preview)
    details = format_legacy_merge_details(preview)
    return f"{summary}\n\n---\n\n{details}"
