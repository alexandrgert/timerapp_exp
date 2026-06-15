# Кросс-платформенная архитектура TaskTimer link B24

Документ описывает целевую модель для **Windows, macOS, Linux, Android, iOS** с опорой на текущий код (Python + PySide6 desktop, WebDAV sync, локальные секреты).

## Принцип

**Один контракт данных, несколько оболочек.**

| Слой | Содержимое | Реализация сегодня |
|------|------------|-------------------|
| **Domain** | модели, merge, таймер, план, напоминания | `src/timerapp_ag/domain/` |
| **Application** | orchestration, save/load, sync hooks | `controller.py` |
| **Adapters** | файлы, WebDAV, Bitrix REST | `storage.py`, `webdav_*`, `bitrix.py` |
| **Shell** | UI, tray, single-instance | `main_window.py`, `main.py` |
| **Platform** | пути, OS-интеграции | `platform_paths.py` |

Mobile (Android/iOS) — **отдельные нативные клиенты**, использующие тот же `data.json` и правила merge, без Python/Qt.

## Пути данных (desktop)

Модуль `platform_paths.py` — единая точка для путей:

| Назначение | Linux | macOS | Windows |
|------------|-------|-------|---------|
| Данные | `~/.local/share/timerapp/TaskTimer link B24/data.json` | `~/Library/Application Support/timerapp/...` | `%LOCALAPPDATA%\timerapp\...` |
| Секреты | `~/.config/tasktimer/` | `~/Library/Application Support/TaskTimer/` | `%APPDATA%\TaskTimer\` |
| `.env` | `~/.config/tasktimer/.env` | то же | `%APPDATA%\TaskTimer\.env` |

Файлы секретов (не синхронизируются):

- `bitrix.json` — webhook Битрикс24
- `webdav.json` — учётные данные WebDAV

## Синхронизация

- **Синхронизируется:** `data.json` (задачи, сессии, `ui` без секретов)
- **Транспорт:** WebDAV (PUT/GET), merge по `task.id`
- **Конфликт задач:** побеждает запись с большим числом sessions; при равенстве — более поздний `created_at`
- **UI при merge:** берётся из «самого полного» файла (больше задач / больше размер)

Контракт формата: [`data-schema.md`](data-schema.md), JSON Schema: [`schemas/data.schema.json`](schemas/data.schema.json).

Алгоритм WebDAV (pull-before-push, versioning, конфликты): [`webdav-sync.md`](webdav-sync.md).

## Desktop (Win / macOS / Linux)

Одна кодовая база PySide6:

| Платформа | Сборка | Артефакт |
|-----------|--------|----------|
| **Windows** | `build_exe.ps1` | `TaskTimer.exe` |
| **Linux** | `build_deb.sh` | `.deb` **amd64** |
| **macOS** | план | `.app` bundle + codesign |

**Linux:** единственный формат дистрибуции — **Debian-пакет amd64** (`dpkg-deb`). Flatpak, AppImage и другие store-форматы **не используются**. Сборка — на x86_64; CI: job `build-deb` в `.github/workflows/ci.yml`.

```bash
./build_deb.sh
```

Подробности WebDAV: [`webdav-sync.md`](webdav-sync.md).

Платформенные отличия — тонкий слой (`platform_paths`, native menu bar на macOS, tray).

## Mobile (Android / iOS) — план

| | Android | iOS |
|---|---------|-----|
| UI | Kotlin + Compose | Swift + SwiftUI |
| Хранилище | Room/SQLite + export `data.json` | SwiftData/SQLite |
| Секреты | EncryptedSharedPrefs / Keystore | Keychain |
| Фоновый таймер | Foreground Service + notification | Live Activity + BG tasks |
| Sync | WebDAV (те же merge-правила) | WebDAV |

Python-код **не портируется** на mobile; портируется **контракт** (`data.schema.json`) и **логика merge** (переписать на Kotlin/Swift с теми же тест-кейсами).

## Дорожная карта

### Фаза A (текущая) — укрепление desktop

- [x] `platform_paths.py`
- [x] `domain/` — бизнес-логика без Qt
- [x] JSON Schema для `data.json`
- [x] Linux `.deb` amd64 (x64) — `build_deb.sh`
- [ ] macOS `.app` bundle

### Фаза B — mobile MVP

- Android: задачи, таймер, WebDAV, Bitrix import
- iOS: то же + Live Activity

### Фаза C — паритет

- Widgets, push «продолжать?», UI разрешения конфликтов sync

## Структура пакетов

```
src/timerapp_ag/
  domain/           # без I/O и без Qt
    state.py        # AppState
    merge.py        # merge_states, pick_best_data_file
    queries.py      # выборки задач
    task_ops.py     # start/stop/create/...
    plan.py         # rollover, schema migration
    reminders.py    # напоминания, focus timer
    formatting.py   # format_duration, ...
  platform_paths.py
  controller.py     # application layer
  storage.py        # persistence
  main_window.py    # Qt shell
```

## Что не делать

- Один PySide6 бинарник на Android/iOS
- PWA как единственный mobile-клиент (ненадёжный фоновый таймер)
- Flatpak / AppImage для Linux (только `.deb` amd64)
- Хранение webhook в `data.json`
- Разные schema на платформах
