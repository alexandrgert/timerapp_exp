# Desktop Title Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Поиск по заголовку задач поверх текущего вида/приоритетов на desktop.

**Architecture:** Domain helper `filter_tasks_by_title` + ephemeral `MainWindow._title_search` + `QLineEdit` в subbar; не писать в `data.json`.

**Tech Stack:** Python 3.12, PySide6, pytest.

## Global Constraints

- Версия: bump **minor** при `./build_deb.sh` (новая фича).
- APK локально не собирать.
- Android вне scope.

---

### Task 1: Domain filter + tests

**Files:** `src/timerapp_ag/domain/queries.py`, `tests/test_title_search.py` (create)

- [x] Write failing tests (casefold, empty needle, order preserved)
- [x] Implement `filter_tasks_by_title`
- [x] Run `.venv/bin/pytest tests/test_title_search.py -q`

### Task 2: MainWindow UI wiring

**Files:** `src/timerapp_ag/main_window.py`, `tests/test_main_window_ui.py`

- [x] Add search field + apply filter in `_rebuild_task_list`
- [x] UI test: search filters rows; survives `_set_view`
- [x] Run UI + domain tests

### Task 3: Docs touch + deb

**Files:** `ИНСТРУКЦИЯ.md` (кратко)

- [x] Mention search in desktop section
- [x] `BUMP=minor ./build_deb.sh`
