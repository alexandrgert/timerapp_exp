"""Локальные настройки приложения (не в data.json / WebDAV)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .platform_paths import config_dir
from .secure_files import write_json_secrets

logger = logging.getLogger(__name__)

MIN_UPDATE_CHECK_INTERVAL_DAYS = 1
MAX_UPDATE_CHECK_INTERVAL_DAYS = 30
DEFAULT_UPDATE_CHECK_INTERVAL_DAYS = 1
DEFAULT_UPDATE_GITHUB_REPO = "alexandrgert/timerapp_exp"


@dataclass
class AppPrefs:
    check_updates: bool = False
    update_check_interval_days: int = DEFAULT_UPDATE_CHECK_INTERVAL_DAYS
    update_github_repo: str = DEFAULT_UPDATE_GITHUB_REPO
    last_update_check_at: str = ""
    dismissed_update_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> AppPrefs:
        payload = data if isinstance(data, dict) else {}
        interval = int(payload.get("update_check_interval_days") or DEFAULT_UPDATE_CHECK_INTERVAL_DAYS)
        interval = max(
            MIN_UPDATE_CHECK_INTERVAL_DAYS,
            min(MAX_UPDATE_CHECK_INTERVAL_DAYS, interval),
        )
        return cls(
            check_updates=bool(payload.get("check_updates", False)),
            update_check_interval_days=interval,
            update_github_repo=normalize_github_repo(
                str(payload.get("update_github_repo") or DEFAULT_UPDATE_GITHUB_REPO)
            ),
            last_update_check_at=str(payload.get("last_update_check_at") or ""),
            dismissed_update_version=str(payload.get("dismissed_update_version") or ""),
        )


def normalize_github_repo(value: str) -> str:
    text = (value or "").strip().removeprefix("https://github.com/").removeprefix("http://github.com/")
    text = text.strip("/")
    if text.count("/") != 1:
        return DEFAULT_UPDATE_GITHUB_REPO
    owner, name = text.split("/", 1)
    owner = owner.strip()
    name = name.strip().removesuffix(".git")
    if not owner or not name:
        return DEFAULT_UPDATE_GITHUB_REPO
    if not all(part.replace("-", "").replace("_", "").replace(".", "").isalnum() for part in (owner, name)):
        return DEFAULT_UPDATE_GITHUB_REPO
    return f"{owner}/{name}"


def app_prefs_path() -> Path:
    return config_dir() / "app.json"


def load_app_prefs() -> AppPrefs:
    path = app_prefs_path()
    if not path.is_file():
        return AppPrefs()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load app prefs: %s", exc)
        return AppPrefs()
    return AppPrefs.from_dict(payload if isinstance(payload, dict) else {})


def save_app_prefs(prefs: AppPrefs) -> None:
    write_json_secrets(app_prefs_path(), prefs.to_dict())


def parse_iso_datetime(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def should_run_auto_update_check(
    prefs: AppPrefs,
    *,
    now: datetime | None = None,
) -> bool:
    if not prefs.check_updates:
        return False
    stamp = now or datetime.now(timezone.utc)
    last = parse_iso_datetime(prefs.last_update_check_at)
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    elapsed = stamp - last
    return elapsed.total_seconds() >= prefs.update_check_interval_days * 86400


def mark_update_check_done(
    prefs: AppPrefs,
    *,
    now: datetime | None = None,
    dismissed_version: str | None = None,
) -> AppPrefs:
    stamp = now or datetime.now(timezone.utc)
    updated = AppPrefs(
        check_updates=prefs.check_updates,
        update_check_interval_days=prefs.update_check_interval_days,
        update_github_repo=normalize_github_repo(prefs.update_github_repo),
        last_update_check_at=stamp.astimezone(timezone.utc).isoformat(),
        dismissed_update_version=(
            dismissed_version
            if dismissed_version is not None
            else prefs.dismissed_update_version
        ),
    )
    save_app_prefs(updated)
    return updated
