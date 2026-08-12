"""Проверка новой версии на GitHub Releases."""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .app_info import resolve_app_version_label
from .app_prefs import DEFAULT_UPDATE_GITHUB_REPO, normalize_github_repo

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^v?(?P<version>\d+(?:\.\d+)*)", re.IGNORECASE)


@dataclass(frozen=True)
class LatestRelease:
    tag_name: str
    version: str
    html_url: str


@dataclass(frozen=True)
class UpdateCheckResult:
    ok: bool
    error: str = ""
    current_version: str = ""
    latest: LatestRelease | None = None
    update_available: bool = False
    github_repo: str = DEFAULT_UPDATE_GITHUB_REPO


def latest_release_api_url(repo: str = DEFAULT_UPDATE_GITHUB_REPO) -> str:
    normalized = normalize_github_repo(repo)
    return f"https://api.github.com/repos/{normalized}/releases/latest"


def normalize_version(tag_or_version: str) -> str:
    text = (tag_or_version or "").strip()
    match = _VERSION_RE.match(text)
    if not match:
        return text.lstrip("vV")
    return match.group("version")


def version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in normalize_version(version).split("."):
        if not chunk.isdigit():
            break
        parts.append(int(chunk))
    return tuple(parts) if parts else (0,)


def is_newer(current: str, remote: str) -> bool:
    return version_tuple(remote) > version_tuple(current)


def parse_latest_release_payload(
    payload: dict,
    *,
    github_repo: str = DEFAULT_UPDATE_GITHUB_REPO,
) -> LatestRelease:
    tag_name = str(payload.get("tag_name") or "").strip()
    html_url = str(payload.get("html_url") or "").strip()
    version = normalize_version(tag_name)
    if not tag_name or not version:
        raise ValueError("Некорректный ответ GitHub Releases")
    repo = normalize_github_repo(github_repo)
    if not html_url:
        html_url = f"https://github.com/{repo}/releases/tag/{tag_name}"
    return LatestRelease(tag_name=tag_name, version=version, html_url=html_url)


def fetch_latest_release(
    *,
    github_repo: str = DEFAULT_UPDATE_GITHUB_REPO,
    url: str | None = None,
    current_version: str | None = None,
    opener: Callable[[urllib.request.Request], object] | None = None,
) -> LatestRelease:
    repo = normalize_github_repo(github_repo)
    request_url = url or latest_release_api_url(repo)
    current = normalize_version(current_version or resolve_app_version_label())
    request = urllib.request.Request(
        request_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"timerapp-exp/{current}",
        },
        method="GET",
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(request) as response:  # type: ignore[arg-type]
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Некорректный ответ GitHub Releases")
    return parse_latest_release_payload(data, github_repo=repo)


def check_for_update(
    *,
    current_version: str | None = None,
    dismissed_version: str = "",
    respect_dismissed: bool = True,
    github_repo: str = DEFAULT_UPDATE_GITHUB_REPO,
    fetch: Callable[[], LatestRelease] | None = None,
) -> UpdateCheckResult:
    current = normalize_version(current_version or resolve_app_version_label())
    repo = normalize_github_repo(github_repo)
    try:
        latest = (
            fetch
            or (lambda: fetch_latest_release(github_repo=repo, current_version=current))
        )()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as exc:
        logger.info("Update check failed: %s", exc)
        return UpdateCheckResult(ok=False, error=str(exc), current_version=current, github_repo=repo)
    except Exception as exc:  # noqa: BLE001 — сеть/парсинг не должны ронять UI
        logger.info("Update check failed: %s", exc)
        return UpdateCheckResult(ok=False, error=str(exc), current_version=current, github_repo=repo)

    available = is_newer(current, latest.version)
    if respect_dismissed and available and normalize_version(dismissed_version) == latest.version:
        available = False
    return UpdateCheckResult(
        ok=True,
        current_version=current,
        latest=latest,
        update_available=available,
        github_repo=repo,
    )
