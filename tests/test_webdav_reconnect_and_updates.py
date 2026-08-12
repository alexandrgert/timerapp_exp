"""Unit tests for WebDAV sync log, reconnect gate, update check."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from timerapp_ag.app_prefs import (
    AppPrefs,
    load_app_prefs,
    mark_update_check_done,
    save_app_prefs,
    should_run_auto_update_check,
)
from timerapp_ag.update_check import (
    LatestRelease,
    check_for_update,
    is_newer,
    normalize_version,
    parse_latest_release_payload,
)
from timerapp_ag.webdav_reconnect import WebDavReconnectGate
from timerapp_ag.webdav_sync_log import (
    append_entry,
    clear_log,
    count_tasks_in_payload,
    format_for_display,
    read_entries,
)


def test_count_tasks_in_payload() -> None:
    assert count_tasks_in_payload(b'{"tasks":[{},{}]}') == 2
    assert count_tasks_in_payload(b"{}") == 0
    assert count_tasks_in_payload(b"not-json") == 0


def test_sync_log_ring_and_format(tmp_path: Path) -> None:
    path = tmp_path / "webdav-sync.log"
    append_entry("push", uploaded_tasks=3, downloaded_tasks=2, path=path)
    append_entry("pull", downloaded_tasks=5, path=path)
    append_entry("reconnect_push", ok=False, error="timeout", uploaded_tasks=1, path=path)
    entries = read_entries(path=path)
    assert len(entries) == 3
    assert entries[-1].ok is False
    text = format_for_display(path=path)
    assert "↑3" in text
    assert "↓5" in text
    assert "ОШИБКА: timeout" in text
    clear_log(path=path)
    assert read_entries(path=path) == []


def test_reconnect_gate_edge_debounce_cooldown() -> None:
    gate = WebDavReconnectGate(debounce_seconds=2.5, cooldown_seconds=60.0)
    assert gate.mark_online(now=100.0) is False
    gate.mark_offline()
    assert gate.mark_online(now=101.0) is True
    assert gate.should_fire_push(now=102.0) is False
    assert gate.should_fire_push(now=104.0) is True
    assert gate.begin_push(now=104.0) is True
    gate.end_push(now=104.0)
    gate.mark_offline()
    assert gate.mark_online(now=120.0) is False  # cooldown
    assert gate.mark_online(now=170.0) is True


def test_reconnect_gate_defers_while_busy() -> None:
    gate = WebDavReconnectGate(debounce_seconds=2.5, cooldown_seconds=60.0)
    gate.mark_offline()
    assert gate.on_online(busy=True, now=100.0) is False
    assert gate.deferred_while_busy is True
    assert gate.was_offline is True
    assert gate.on_busy_finished(now=101.0) is True
    assert gate.should_fire_push(now=104.0) is True
    # debounce fired but sync still busy — keep edge
    gate.defer_fire_until_idle()
    assert gate.deferred_while_busy is True
    assert gate.begin_push(now=110.0) is False
    assert gate.on_busy_finished(now=111.0) is True
    assert gate.begin_push(now=114.0) is True
    gate.end_push(now=114.0)


def test_version_compare_and_parse() -> None:
    assert normalize_version("v0.9.2") == "0.9.2"
    assert is_newer("0.9.1", "0.9.2") is True
    assert is_newer("0.9.2", "0.9.2") is False
    release = parse_latest_release_payload(
        {"tag_name": "v1.2.0", "html_url": "https://example/release"}
    )
    assert release.version == "1.2.0"


def test_check_for_update_respects_dismissed() -> None:
    latest = LatestRelease(tag_name="v0.9.5", version="0.9.5", html_url="https://x")
    result = check_for_update(
        current_version="0.9.1",
        dismissed_version="0.9.5",
        respect_dismissed=True,
        fetch=lambda: latest,
    )
    assert result.ok is True
    assert result.update_available is False
    manual = check_for_update(
        current_version="0.9.1",
        dismissed_version="0.9.5",
        respect_dismissed=False,
        fetch=lambda: latest,
    )
    assert manual.update_available is True


def test_normalize_github_repo() -> None:
    from timerapp_ag.app_prefs import normalize_github_repo

    assert normalize_github_repo("alexandrgert/timer-app") == "alexandrgert/timer-app"
    assert normalize_github_repo("https://github.com/alexandrgert/timerapp_exp") == (
        "alexandrgert/timerapp_exp"
    )
    assert normalize_github_repo("bad") == "alexandrgert/timerapp_exp"


def test_app_prefs_auto_check_interval(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "app.json"
    monkeypatch.setattr("timerapp_ag.app_prefs.app_prefs_path", lambda: path)
    prefs = AppPrefs(check_updates=False, update_check_interval_days=1)
    save_app_prefs(prefs)
    loaded = load_app_prefs()
    assert loaded.check_updates is False
    assert should_run_auto_update_check(loaded) is False

    loaded.check_updates = True
    assert should_run_auto_update_check(loaded) is True
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    updated = mark_update_check_done(loaded, now=now)
    assert should_run_auto_update_check(updated, now=now) is False
    assert should_run_auto_update_check(
        updated, now=now + timedelta(days=1, seconds=1)
    ) is True
    assert loaded.update_github_repo == "alexandrgert/timerapp_exp"
