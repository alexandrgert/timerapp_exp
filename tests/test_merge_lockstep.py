"""Lockstep richer-session rules for desktop ↔ Android WebDAV merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from timerapp_ag.domain.merge import _pick_richer_session, merge_task_pair
from timerapp_ag.models import Session, Task, TaskStatus

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "merge_lockstep"


def _closed(
    sid: str,
    minutes: int,
    *,
    comment: str = "",
    bitrix: str | None = None,
) -> Session:
    start_h, start_m = 10, 0
    total = start_h * 60 + start_m + minutes
    end_h, end_m = divmod(total, 60)
    return Session(
        id=sid,
        started_at=f"2026-07-10T{start_h:02d}:{start_m:02d}:00+03:00",
        ended_at=f"2026-07-10T{end_h:02d}:{end_m:02d}:00+03:00",
        comment=comment,
        bitrix_record_id=bitrix,
    )


def _task(session: Session) -> Task:
    return Task(
        id="t1",
        day="2026-07-10",
        title="A",
        created_at="2026-07-10T09:00:00+03:00",
        status=TaskStatus.PAUSED,
        sessions=[session],
    )


def test_equal_duration_prefers_bitrix_over_blank() -> None:
    left = _closed("s1", 30, bitrix="42")
    right = _closed("s1", 30)
    assert _pick_richer_session(left, right).bitrix_record_id == "42"
    assert _pick_richer_session(right, left).bitrix_record_id == "42"


def test_equal_duration_prefers_comment_over_blank() -> None:
    left = _closed("s1", 30, comment="resume reason")
    right = _closed("s1", 30)
    assert _pick_richer_session(left, right).comment == "resume reason"
    assert _pick_richer_session(right, left).comment == "resume reason"


def test_equal_meta_prefers_candidate() -> None:
    left = _closed("s1", 30, comment="a", bitrix="1")
    right = _closed("s1", 30, comment="b", bitrix="2")
    picked = _pick_richer_session(left, right)
    assert picked.comment == "b"
    assert picked.bitrix_record_id == "2"


def test_longer_duration_beats_meta() -> None:
    short = _closed("s1", 10, bitrix="99")
    long = _closed("s1", 60)
    assert _pick_richer_session(short, long).duration_seconds() == 3600
    assert _pick_richer_session(long, short).duration_seconds() == 3600


def test_merge_task_pair_preserves_bitrix_when_peer_blank() -> None:
    merged = merge_task_pair(
        _task(_closed("s1", 30, bitrix="42")),
        _task(_closed("s1", 30)),
    )
    assert merged.sessions[0].bitrix_record_id == "42"


def _load_task(path: Path) -> Task:
    return Task.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _load_session(path: Path) -> Session:
    return Session.from_dict(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "case_name",
    ["case_bitrix_vs_plain", "case_comment_tie"],
)
def test_golden_fixture_session(case_name: str) -> None:
    case_dir = FIXTURES / case_name
    merged = merge_task_pair(_load_task(case_dir / "left.json"), _load_task(case_dir / "right.json"))
    expected = _load_session(case_dir / "expected_session.json")
    assert len(merged.sessions) == 1
    got = merged.sessions[0]
    assert got.id == expected.id
    assert got.started_at == expected.started_at
    assert got.ended_at == expected.ended_at
    assert got.comment == expected.comment
    assert got.bitrix_record_id == expected.bitrix_record_id


def test_golden_fixture_union_two_ids() -> None:
    case_dir = FIXTURES / "case_union_two_ids"
    merged = merge_task_pair(_load_task(case_dir / "left.json"), _load_task(case_dir / "right.json"))
    expected = _load_task(case_dir / "expected_task.json")
    assert [session.id for session in merged.sessions] == [session.id for session in expected.sessions]
    assert [(s.started_at, s.ended_at) for s in merged.sessions] == [
        (s.started_at, s.ended_at) for s in expected.sessions
    ]
