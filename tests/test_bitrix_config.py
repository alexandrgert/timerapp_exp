from __future__ import annotations

from timerapp_ag.bitrix_config import (
    BitrixPortalConfig,
    discover_portal_config,
    merge_portal_config,
)


def test_merge_portal_config_uses_defaults_for_empty():
    config = merge_portal_config(None)
    assert config.projects_entity_type_id == 150
    assert config.projects_executor_fields == ("ufCrm16MainIspolnitel", "ufCrm16Supporters")


def test_portal_config_roundtrip_dict():
    original = BitrixPortalConfig(
        projects_entity_type_id=177,
        projects_executor_fields=("ufCrm18Main", "ufCrm18Team"),
        projects_registry_title="Мои проекты",
    )
    restored = BitrixPortalConfig.from_dict(original.to_dict())
    assert restored == original


def test_discover_portal_config_finds_registry_and_fields():
    def list_types():
        return [
            {"entityTypeId": 2, "title": "Сделки"},
            {"entityTypeId": 177, "title": "Реестр проектов"},
        ]

    def list_fields(entity_type_id: int):
        assert entity_type_id == 177
        return {
            "fields": {
                "ufCrm18MainIspolnitel": {"title": "Главный исполнитель"},
                "ufCrm18Supporters": {"title": "Помощники"},
                "TITLE": {"title": "Название"},
            }
        }

    config = discover_portal_config(
        list_types=list_types,
        list_fields=list_fields,
        preferred_registry_title="Реестр проектов",
    )
    assert config.projects_entity_type_id == 177
    assert "ufCrm18MainIspolnitel" in config.projects_executor_fields
    assert "ufCrm18Supporters" in config.projects_executor_fields
