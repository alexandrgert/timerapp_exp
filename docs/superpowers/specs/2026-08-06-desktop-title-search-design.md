# Desktop title search (поверх фильтров)

**Date:** 2026-08-06  
**Status:** approved  
**Scope:** desktop (PySide6) only; Android later.

## Goal

Быстро сузить список задач по подстроке в **заголовке**, не меняя текущий вид (Сегодня / В работе / Все / дата) и фильтр приоритетов.

## Behaviour

1. Поле ввода в subbar после `QDateEdit`, до stretch.
2. Placeholder: «Поиск по названию…».
3. Фильтр: `needle.strip().casefold()` входит в `task.title.casefold()`; пустой needle — без доп. фильтра.
4. Применяется **после** выбора вида и приоритетов (поверх).
5. Состояние: `MainWindow._title_search` (ephemeral). При смене вкладок/даты — сброс поля и фильтра. При рестарте приложения — тоже пусто. В `data.json` / WebDAV **не** пишется.
6. Пустой список после поиска: существующий `_empty_hint()` + при непустом поиске можно уточнить «Ничего не найдено по запросу.» (опционально, предпочтительно).

## Non-goals

- Поиск по description / result / сессиям.
- Android UI.
- Persist запроса.

## Implementation sketch

- `domain/queries.py`: `filter_tasks_by_title(tasks: list[Task], needle: str) -> list[Task]`
- `main_window.py`: `QLineEdit` → `_on_title_search_changed` → `refresh_ui` / rebuild list
- Tests: domain unit + UI (`test_main_window_ui.py`)

## Acceptance

- В «Все» с двумя задачами «Alpha» / «Beta» поиск `alp` показывает только Alpha.
- Переключение Сегодня → Все сохраняет текст в поле и продолжает фильтровать.
- После перезапуска поле пустое.
