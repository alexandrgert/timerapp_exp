from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from .domain.datetime_util import duration_seconds, parse_iso_datetime


class TaskStatus(str, Enum):
    OPEN = "open"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


def make_id() -> str:
    return uuid4().hex


@dataclass
class Session:
    id: str
    started_at: str
    ended_at: str | None = None
    bitrix_record_id: str | None = None
    comment: str = ""

    @property
    def start_dt(self) -> datetime:
        return parse_iso_datetime(self.started_at)

    @property
    def end_dt(self) -> datetime | None:
        return parse_iso_datetime(self.ended_at) if self.ended_at else None

    def duration_seconds(self, now: datetime | None = None) -> int:
        return duration_seconds(self.started_at, self.ended_at, now=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "bitrix_record_id": self.bitrix_record_id,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            id=data["id"],
            started_at=data["started_at"],
            ended_at=data.get("ended_at"),
            bitrix_record_id=data.get("bitrix_record_id"),
            comment=str(data.get("comment", "") or ""),
        )


@dataclass
class Task:
    id: str
    day: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.OPEN
    sessions: list[Session] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None
    continuation_of: str | None = None
    bitrix: dict[str, Any] | None = None
    planned_days: list[str] = field(default_factory=list)
    daily_priorities: dict[str, int] = field(default_factory=dict)

    def total_seconds(self, now: datetime | None = None) -> int:
        return sum(session.duration_seconds(now=now) for session in self.sessions)

    def active_session(self) -> Session | None:
        for session in reversed(self.sessions):
            if session.ended_at is None:
                return session
        return None

    def is_completed(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "day": self.day,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "sessions": [session.to_dict() for session in self.sessions],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "continuation_of": self.continuation_of,
            "bitrix": self.bitrix,
            "planned_days": self.planned_days,
        }
        if self.daily_priorities:
            payload["daily_priorities"] = dict(self.daily_priorities)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            day=data["day"],
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", TaskStatus.OPEN.value)),
            sessions=[Session.from_dict(item) for item in data.get("sessions", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            completed_at=data.get("completed_at"),
            continuation_of=data.get("continuation_of"),
            bitrix=data.get("bitrix"),
            planned_days=list(data.get("planned_days") or []),
            daily_priorities={
                str(key): int(value)
                for key, value in (data.get("daily_priorities") or {}).items()
                if isinstance(value, int) and 1 <= value <= 4
            },
        )
