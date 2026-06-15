# Контракт data.json (schema v2)

Файл `data.json` — единый формат обмена между desktop, WebDAV и будущими mobile-клиентами.

**Machine-readable:** [`schemas/data.schema.json`](schemas/data.schema.json) (JSON Schema draft 2020-12).

## Версия

- `ui.schema_version`: **2** (persistent tasks + daily plan)
- Клиенты с версией `< 2` должны выполнить миграцию (см. `domain/plan.py::migrate_schema_v2`)

## Корневая структура

```json
{
  "tasks": [ /* Task[] */ ],
  "ui": { /* UISettings */ }
}
```

## Task

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `id` | string | да | UUID hex (32 символа) |
| `day` | string | да | ISO date `YYYY-MM-DD` — день создания |
| `title` | string | да | Название |
| `description` | string | нет | Описание |
| `status` | enum | да | `open`, `running`, `paused`, `completed` |
| `sessions` | Session[] | да | Интервалы учёта времени |
| `created_at` | string | нет | ISO 8601 datetime |
| `completed_at` | string \| null | нет | ISO 8601 datetime |
| `continuation_of` | string \| null | нет | legacy, schema v1 |
| `bitrix` | object \| null | нет | `{"source": "task"\|"project", "id": "..."}` |
| `planned_days` | string[] | нет | ISO dates — план на день |

## Session

| Поле | Тип | Обязательно |
|------|-----|-------------|
| `id` | string | да |
| `started_at` | string (ISO 8601) | да |
| `ended_at` | string \| null | нет — `null` = таймер идёт |

## UI (`ui`)

| Поле | Тип | Sync | Описание |
|------|-----|------|----------|
| `schema_version` | int | да | 2 |
| `plan_rollover_day` | string | да | последний rollover плана |
| `filter_open_only` | bool | да | фильтр списка |
| `reminder_interval_minutes` | int | да | 1…1440 |
| `focus_timer` | object | да | `{selected_minutes, duration_minutes, ends_at}` |
| `bitrix.portal` | object | да | настройки СПА (не секрет) |
| `bitrix.webhook_url` | — | **запрещено** | только локально в `bitrix.json` |

## Merge при синхронизации

1. Загрузить все известные `data.json` (локальные + remote WebDAV).
2. UI взять из файла с max `(task_count, file_size)`.
3. Tasks объединить по `id`; при конфликте — запись с большим `len(sessions)`, затем более поздний `created_at`.
4. Перед сохранением удалить `ui.bitrix.webhook_url`.

## Секреты (не в data.json)

| Файл | Содержимое |
|------|------------|
| `bitrix.json` | `{"webhook_url": "https://..."}` |
| `webdav.json` | URL, username, password, flags sync |

Пути — см. `platform_paths.py` и [`architecture-cross-platform.md`](architecture-cross-platform.md).

## Пример минимального файла

```json
{
  "tasks": [],
  "ui": {
    "schema_version": 2,
    "filter_open_only": false,
    "reminder_interval_minutes": 40,
    "focus_timer": {
      "selected_minutes": 20,
      "duration_minutes": null,
      "ends_at": null
    }
  }
}
```
