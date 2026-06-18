from __future__ import annotations

from datetime import datetime

from timerapp_ag.models import Session, Task, TaskStatus, make_id


def test_make_id_is_unique() -> None:
    assert make_id() != make_id()


def test_session_duration_for_closed_interval() -> None:
    session = Session(
        id="s1",
        started_at="2026-01-01T10:00:00",
        ended_at="2026-01-01T10:30:00",
    )
    assert session.duration_seconds() == 30 * 60


def test_session_duration_for_open_interval_uses_now() -> None:
    start = datetime(2026, 1, 1, 10, 0, 0)
    now = datetime(2026, 1, 1, 10, 0, 45)
    session = Session(id="s1", started_at=start.isoformat())
    assert session.duration_seconds(now=now) == 45


def test_session_duration_never_negative() -> None:
    session = Session(
        id="s1",
        started_at="2026-01-01T10:30:00",
        ended_at="2026-01-01T10:00:00",
    )
    assert session.duration_seconds() == 0


def test_session_bitrix_record_id_round_trip() -> None:
    session = Session(
        id="s1",
        started_at="2026-01-01T10:00:00",
        ended_at="2026-01-01T10:30:00",
        bitrix_record_id="999",
    )
    restored = Session.from_dict(session.to_dict())
    assert restored.bitrix_record_id == "999"


def test_session_from_dict_without_comment_defaults_empty() -> None:
    restored = Session.from_dict(
        {
            "id": "s1",
            "started_at": "2026-01-01T10:00:00",
            "ended_at": "2026-01-01T10:30:00",
        }
    )
    assert restored.comment == ""


def test_session_comment_round_trip() -> None:
    session = Session(
        id="s1",
        started_at="2026-01-01T10:00:00",
        ended_at="2026-01-01T10:30:00",
        comment="Созвон с клиентом",
    )
    restored = Session.from_dict(session.to_dict())
    assert restored.comment == "Созвон с клиентом"


def test_task_total_seconds_sums_sessions() -> None:
    task = Task(
        id="t1",
        day="2026-01-01",
        title="T",
        sessions=[
            Session(id="a", started_at="2026-01-01T10:00:00", ended_at="2026-01-01T10:10:00"),
            Session(id="b", started_at="2026-01-01T11:00:00", ended_at="2026-01-01T11:05:00"),
        ],
    )
    assert task.total_seconds() == 15 * 60


def test_active_session_returns_open_one() -> None:
    open_session = Session(id="b", started_at="2026-01-01T11:00:00")
    task = Task(
        id="t1",
        day="2026-01-01",
        title="T",
        sessions=[
            Session(id="a", started_at="2026-01-01T10:00:00", ended_at="2026-01-01T10:10:00"),
            open_session,
        ],
    )
    assert task.active_session() is open_session


def test_active_session_returns_none_when_all_closed() -> None:
    task = Task(
        id="t1",
        day="2026-01-01",
        title="T",
        sessions=[Session(id="a", started_at="2026-01-01T10:00:00", ended_at="2026-01-01T10:10:00")],
    )
    assert task.active_session() is None


def test_task_round_trip_serialization() -> None:
    task = Task(
        id="t1",
        day="2026-01-01",
        title="Demo",
        description="desc",
        status=TaskStatus.PAUSED,
        sessions=[Session(id="a", started_at="2026-01-01T10:00:00", ended_at="2026-01-01T10:10:00")],
        continuation_of="prev",
    )
    restored = Task.from_dict(task.to_dict())
    assert restored == task


def test_task_from_dict_applies_defaults() -> None:
    restored = Task.from_dict({"id": "t1", "day": "2026-01-01", "title": "Bare"})
    assert restored.description == ""
    assert restored.status == TaskStatus.OPEN
    assert restored.sessions == []
    assert restored.continuation_of is None
