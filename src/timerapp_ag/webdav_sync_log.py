"""Локальный журнал операций WebDAV (не синхронизируется в облако)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .platform_paths import config_dir

logger = logging.getLogger(__name__)

MAX_ENTRIES = 200
LOG_FILENAME = "webdav-sync.log"


@dataclass(frozen=True)
class SyncLogEntry:
    ts: str
    op: str
    uploaded_tasks: int = 0
    downloaded_tasks: int = 0
    ok: bool = True
    error: str = ""

    def display_line(self) -> str:
        status = "OK" if self.ok else f"ОШИБКА: {self.error}"
        return (
            f"{self.ts}  {self.op:<16}  "
            f"↑{self.uploaded_tasks}  ↓{self.downloaded_tasks}  {status}"
        )


def sync_log_path() -> Path:
    return config_dir() / LOG_FILENAME


def count_tasks_in_payload(payload: bytes | str | None) -> int:
    if payload is None:
        return 0
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not raw:
        return 0
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(data, dict):
        return 0
    tasks = data.get("tasks")
    return len(tasks) if isinstance(tasks, list) else 0


def append_entry(
    op: str,
    *,
    uploaded_tasks: int = 0,
    downloaded_tasks: int = 0,
    ok: bool = True,
    error: str = "",
    path: Path | None = None,
    now: datetime | None = None,
) -> SyncLogEntry:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    entry = SyncLogEntry(
        ts=stamp,
        op=op,
        uploaded_tasks=max(0, int(uploaded_tasks)),
        downloaded_tasks=max(0, int(downloaded_tasks)),
        ok=ok,
        error=(error or "").strip() if not ok else "",
    )
    target = path or sync_log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        entries = read_entries(path=target)
        entries.append(entry)
        if len(entries) > MAX_ENTRIES:
            entries = entries[-MAX_ENTRIES:]
        with target.open("w", encoding="utf-8") as handle:
            for item in entries:
                handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Failed to write WebDAV sync log: %s", exc)
    return entry


def read_entries(*, path: Path | None = None) -> list[SyncLogEntry]:
    target = path or sync_log_path()
    if not target.is_file():
        return []
    entries: list[SyncLogEntry] = []
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read WebDAV sync log: %s", exc)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        entries.append(
            SyncLogEntry(
                ts=str(payload.get("ts") or ""),
                op=str(payload.get("op") or ""),
                uploaded_tasks=int(payload.get("uploaded_tasks") or 0),
                downloaded_tasks=int(payload.get("downloaded_tasks") or 0),
                ok=bool(payload.get("ok", True)),
                error=str(payload.get("error") or ""),
            )
        )
    return entries


def format_for_display(*, path: Path | None = None) -> str:
    entries = read_entries(path=path)
    if not entries:
        return "Журнал пуст."
    return "\n".join(entry.display_line() for entry in entries)


def clear_log(*, path: Path | None = None) -> None:
    target = path or sync_log_path()
    try:
        if target.is_file():
            target.unlink()
    except OSError as exc:
        logger.warning("Failed to clear WebDAV sync log: %s", exc)
