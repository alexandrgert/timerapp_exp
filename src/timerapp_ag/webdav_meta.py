"""Метаданные WebDAV-sync: хеш содержимого и revision для conflict detection."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4


META_SUFFIX = ".sync-meta.json"


@dataclass
class RemoteSyncMeta:
    content_hash: str
    revision: str
    updated_at: str
    device_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "device_id": self.device_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RemoteSyncMeta | None:
        if not isinstance(data, dict):
            return None
        content_hash = str(data.get("content_hash") or "").strip()
        if not content_hash:
            return None
        return cls(
            content_hash=content_hash,
            revision=str(data.get("revision") or "").strip() or content_hash[:16],
            updated_at=str(data.get("updated_at") or "").strip(),
            device_id=str(data.get("device_id") or "").strip(),
        )


def content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def meta_remote_path(data_remote_path: str) -> str:
    path = data_remote_path.strip()
    if path.endswith(".json"):
        return path[: -len(".json")] + META_SUFFIX
    return path.rstrip("/") + META_SUFFIX


def new_revision() -> str:
    return uuid4().hex


def new_meta(payload: bytes, device_id: str) -> RemoteSyncMeta:
    now = datetime.now().isoformat(timespec="seconds")
    digest = content_hash(payload)
    return RemoteSyncMeta(
        content_hash=digest,
        revision=new_revision(),
        updated_at=now,
        device_id=device_id,
    )


def parse_meta_bytes(payload: bytes) -> RemoteSyncMeta | None:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return RemoteSyncMeta.from_dict(data)


def meta_to_bytes(meta: RemoteSyncMeta) -> bytes:
    return json.dumps(meta.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
