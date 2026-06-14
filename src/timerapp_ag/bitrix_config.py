"""Bitrix24 portal-specific settings (SPA projects registry, filter fields).

Defaults match the original webmens portal (СПА 150 «Реестр проектов»).
Values are persisted in ``ui.bitrix.portal`` and can be auto-discovered from
the portal via ``discover_portal_config``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# Original portal: smart-process «Реестр проектов» (entityTypeId 150).
DEFAULT_PROJECTS_ENTITY_TYPE_ID = 150
DEFAULT_PROJECTS_EXECUTOR_FIELDS = ("ufCrm16MainIspolnitel", "ufCrm16Supporters")
DEFAULT_PROJECTS_REGISTRY_TITLE = "Реестр проектов"

_EXECUTOR_KEYWORDS = ("главн", "исполнител", "main")
_SUPPORTER_KEYWORDS = ("помощник", "supporter", "соисполнител", "участник")


@dataclass(frozen=True)
class BitrixPortalConfig:
    projects_entity_type_id: int = DEFAULT_PROJECTS_ENTITY_TYPE_ID
    projects_executor_fields: tuple[str, ...] = DEFAULT_PROJECTS_EXECUTOR_FIELDS
    projects_registry_title: str = DEFAULT_PROJECTS_REGISTRY_TITLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "projects_entity_type_id": self.projects_entity_type_id,
            "projects_executor_fields": list(self.projects_executor_fields),
            "projects_registry_title": self.projects_registry_title,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BitrixPortalConfig:
        if not isinstance(data, dict):
            return cls()
        raw_fields = data.get("projects_executor_fields")
        fields: tuple[str, ...]
        if isinstance(raw_fields, list) and raw_fields:
            fields = tuple(str(item) for item in raw_fields if item)
        else:
            fields = DEFAULT_PROJECTS_EXECUTOR_FIELDS
        try:
            entity_type_id = int(data.get("projects_entity_type_id", DEFAULT_PROJECTS_ENTITY_TYPE_ID))
        except (TypeError, ValueError):
            entity_type_id = DEFAULT_PROJECTS_ENTITY_TYPE_ID
        title = str(data.get("projects_registry_title") or DEFAULT_PROJECTS_REGISTRY_TITLE).strip()
        return cls(
            projects_entity_type_id=entity_type_id,
            projects_executor_fields=fields,
            projects_registry_title=title or DEFAULT_PROJECTS_REGISTRY_TITLE,
        )


def merge_portal_config(stored: dict[str, Any] | None) -> BitrixPortalConfig:
    """Return stored portal config merged over defaults."""
    return BitrixPortalConfig.from_dict(stored)


def _title_matches(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in keywords)


def _pick_spa_type(types: list[dict], preferred_title: str) -> dict | None:
    if not types:
        return None
    preferred = (preferred_title or "").strip().lower()
    if preferred:
        for item in types:
            title = str(item.get("title", "")).strip().lower()
            if title == preferred:
                return item
        for item in types:
            title = str(item.get("title", "")).strip().lower()
            if preferred in title or title in preferred:
                return item
    for item in types:
        title = str(item.get("title", "")).strip().lower()
        if "реестр" in title and "проект" in title:
            return item
    for item in types:
        title = str(item.get("title", "")).strip().lower()
        if "проект" in title:
            return item
    return None


def _field_entries(fields_payload: dict | list) -> list[tuple[str, str]]:
    """Return ``(code, title)`` pairs from ``crm.item.fields`` response."""
    if isinstance(fields_payload, list):
        items = fields_payload
    elif isinstance(fields_payload, dict):
        items = fields_payload.get("fields", fields_payload)
        if isinstance(items, dict):
            return [
                (str(code), str(meta.get("title", meta.get("formLabel", ""))))
                for code, meta in items.items()
                if isinstance(meta, dict)
            ]
        if not isinstance(items, list):
            return []
    else:
        return []
    pairs: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("upperName") or item.get("name") or item.get("code") or "")
        title = str(item.get("title") or item.get("formLabel") or "")
        if code:
            pairs.append((code, title))
    return pairs


def _match_executor_fields(pairs: list[tuple[str, str]]) -> list[str]:
    executors = [code for code, title in pairs if _title_matches(title, _EXECUTOR_KEYWORDS)]
    supporters = [code for code, title in pairs if _title_matches(title, _SUPPORTER_KEYWORDS)]
    matched = executors + [code for code in supporters if code not in executors]
    return matched or list(DEFAULT_PROJECTS_EXECUTOR_FIELDS)


def discover_portal_config(
    *,
    list_types: Callable[[], list[dict]],
    list_fields: Callable[[int], dict | list],
    preferred_registry_title: str = DEFAULT_PROJECTS_REGISTRY_TITLE,
) -> BitrixPortalConfig:
    """Detect SPA projects registry and user-filter fields from the portal."""
    spa = _pick_spa_type(list_types(), preferred_registry_title)
    if spa is None:
        return BitrixPortalConfig(projects_registry_title=preferred_registry_title)
    entity_type_id = int(spa.get("entityTypeId") or DEFAULT_PROJECTS_ENTITY_TYPE_ID)
    title = str(spa.get("title") or preferred_registry_title).strip()
    fields_payload = list_fields(entity_type_id)
    executor_fields = tuple(_match_executor_fields(_field_entries(fields_payload)))
    return BitrixPortalConfig(
        projects_entity_type_id=entity_type_id,
        projects_executor_fields=executor_fields,
        projects_registry_title=title,
    )
