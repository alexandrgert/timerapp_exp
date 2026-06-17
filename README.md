# TaskTimer link B24

Десктопный таймер задач на Python + [PySide6](https://doc.qt.io/qtforpython/) с интеграцией **Битрикс24**: импорт проектов (СПА) и задач, создание задач на портале, синхронизация завершения. **Синхронизация базы задач через WebDAV** (Nextcloud, Яндекс.Диск и др.).

**Fork** [useraitester-creator/win-timer-app-v1](https://github.com/useraitester-creator/win-timer-app-v1) (TaskTimer). От upstream: пакет `timerapp_ag`, WebDAV, Android, `.deb`, расширенная интеграция Bitrix24.

Инструкция для пользователей — [`ИНСТРУКЦИЯ.md`](ИНСТРУКЦИЯ.md). Сборка `.exe` — [`README-DISTRIBUTION.txt`](README-DISTRIBUTION.txt).

## Возможности

- Три вида списка: **план на сегодня**, **в работе**, **все задачи**; фильтр по дате учёта времени.
- Таймер по задачам, история интервалов, напоминание «продолжать?», режим **Фокус** (обратный отсчёт).
- Системный трей и плавающий виджет активной или приостановленной задачи (скрывается после завершения); щелчок по иконке в трее показывает или скрывает главное окно.
- **Объединение баз** от старых версий — по запросу при обновлении или из меню «Настройки».
- **Битрикс24**: импорт проектов/задач, «Открыть в Б24», создание задачи с привязкой к компании, автозавершение на портале, **передача затраченного времени** из истории сессий.
- **WebDAV**: синхронизация `data.json` между компьютерами; настройки в UI или `.env`.
- Настройки СПА «Реестр проектов» — в UI (**Определить с портала**) или в `ui.bitrix.portal` в `data.json`.

Спецификация модели «план на день»: [`docs/superpowers/specs/2026-06-11-task-views-and-plan-design.md`](docs/superpowers/specs/2026-06-11-task-views-and-plan-design.md).

Документация: [архитектура](docs/architecture-cross-platform.md) · [схема данных](docs/data-schema.md) · [WebDAV (техн.)](docs/webdav-sync.md) · [системные требования](docs/system-requirements.md) · [релиз 0.4.4](docs/release-notes-v0.4.4.md)

## Быстрый старт

```bash
git clone https://github.com/alexandrgert/timer-app.git
cd timer-app
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e . -r requirements-dev.txt
cp .env.example .env        # подставьте BITRIX24_HOOK_URL
./run.sh
```

Или после установки:

```bash
timerapp
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

## Сборка дистрибутивов

Минимальные требования для каждой платформы — [`docs/system-requirements.md`](docs/system-requirements.md).

Версия — в **`pyproject.toml`**. При сборке можно автоматически поднять semver (`BUMP=patch|minor|major`) или зафиксировать (`NO_BUMP=1`).

### Windows (`win64.exe`)

```powershell
.\build_exe.ps1
```

Результат: `dist\tasktimer-link-b24-<версия>-win64.exe`. Сборка только на **Windows 10/11 x64**.

### Linux (`.deb` amd64)

Единственный формат дистрибуции для Linux — **Debian-пакет amd64** (не Flatpak).

```bash
./build_deb.sh
```

Требования: `dpkg-deb`, venv, PyInstaller из `requirements-build.txt`, хост **x86_64**.

| Команда | Когда |
|---------|--------|
| `./build_deb.sh` | мелкие правки → **patch** |
| `BUMP=minor ./build_deb.sh` | новые фичи → **minor** |
| `NO_BUMP=1 ./build_deb.sh` | пересборка без смены версии |

Результат: `dist/tasktimer-link-b24-<версия>-amd64.deb`.

### macOS (`.app` в `.zip`)

```bash
./build_macos.sh
```

Результат: `dist/tasktimer-link-b24-<версия>-macos-<arch>.zip` (arm64 или x86_64). Сборка только на **macOS**.

### Android (`.apk`)

```bash
./build_apk.sh
```

Результат: `dist/tasktimer-link-b24-<версия>-android.apk`. См. [системные требования](docs/system-requirements.md).

### CI

При push в `main` GitHub Actions собирает **`.deb`**, **`.exe`** и **macOS `.zip`** (артефакты в workflow run).

Ручной bump без сборки: `python scripts/bump_version.py minor`

### Releases

Готовые сборки — [GitHub Releases](https://github.com/alexandrgert/timer-app/releases).
**Системные требования:** [`docs/system-requirements.md`](docs/system-requirements.md).

**Последний релиз:** [v0.4.4](https://github.com/alexandrgert/timer-app/releases/tag/v0.4.4) — [текст для пользователей](docs/release-notes-v0.4.4.md)

| Платформа | Файл |
|-----------|------|
| Linux amd64 | `tasktimer-link-b24-0.4.4-amd64.deb` |
| Windows x64 | `tasktimer-link-b24-0.4.4-win64.exe` |
| macOS | `tasktimer-link-b24-0.4.4-macos-<arch>.zip` |
| Android | `tasktimer-link-b24-0.4.4-android.apk` |

Linux:

```bash
wget https://github.com/alexandrgert/timer-app/releases/download/v0.4.4/tasktimer-link-b24-0.4.4-amd64.deb
sudo dpkg -i tasktimer-link-b24-0.4.4-amd64.deb
sudo apt-get install -f
tasktimer-link-b24
```

## Зависимости

| Пакет | Назначение |
|-------|------------|
| `PySide6` | UI (Qt) |
| `fast-bitrix24` | пакетные вызовы REST при импорте |
| `python-dotenv` | загрузка `.env` |

## Структура

```
app.py                 # обёртка для запуска
run.sh                 # запуск из venv проекта
build_deb.sh           # сборка .deb (Linux amd64)
build_exe.ps1          # сборка .exe (Windows x64)
build_macos.sh         # сборка .app zip (macOS)
build_apk.sh           # сборка .apk (Android)
src/timerapp_ag/
  main.py              # точка входа
  controller.py        # бизнес-логика
  domain/              # merge, план, напоминания (без Qt)
  main_window.py       # UI, трей, плавающий виджет
  storage.py           # data.json
  legacy_merge*.py     # опциональное слияние баз старых версий
  platform_paths.py    # пути данных и конфигурации
  webdav_*.py          # синхронизация с облаком
  bitrix*.py           # Битрикс24
tests/
docs/                  # архитектура, WebDAV, release notes
```

## Битрикс24

- **Вебхук** — в **Настройках** приложения или в `~/.config/tasktimer/bitrix.json` (не попадает в облако при WebDAV-sync). Можно также задать `BITRIX24_HOOK_URL` в `.env`.
- **Права вебхука**: `task`, `crm`, `user`.
- **Реестр проектов** — смарт-процесс на портале (по умолчанию entityTypeId 150, «Реестр проектов»); поля исполнителя определяются автоматически или через **Настройки → Определить с портала**.
- **Передача времени** — окно **«История» → отметить интервалы → «Передать в Битрикс»**: выбранные непереданные интервалы суммируются в одну запись на портале (проект → журнал работ СПА 1092, задача → `task.elapseditem.add`). Спецификация: [`docs/superpowers/specs/2026-06-11-time-push-to-bitrix-design.md`](docs/superpowers/specs/2026-06-11-time-push-to-bitrix-design.md).

### Логика передачи времени (слияние интервалов)

Учёт времени ведётся по **интервалам** («сессиям»). При передаче в Битрикс24 они **не отправляются по одному**, а **сливаются в единую запись**:

1. Берутся только интервалы, **отмеченные галочками** и **ещё не переданные** (колонка «Передано» пуста).
2. Длительности **суммируются**: `итог = Σ длительностей выбранных непереданных интервалов`.
3. Запрашивается **название** записи (по умолчанию — название задачи).
4. **Одна запись** на портал: задача Битрикс24 → секунды в `task.elapseditem.add`; проект → часы в журнале работ (СПА 1092).
5. Все слитые интервалы помечаются **id записи** — повторная отправка не создаёт дублей.

Пошаговая инструкция — [`ИНСТРУКЦИЯ.md`](ИНСТРУКЦИЯ.md).

## Данные

- **Задачи и UI** — `data.json` в каталоге данных приложения (см. `platform_paths.py` / [data-schema](docs/data-schema.md)).
- **Секреты** (вебхук, пароль WebDAV) — `~/.config/tasktimer/` (`bitrix.json`, `webdav.json`).
- **WebDAV** — опциональная синхронизация `data.json`; см. [ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md) и [webdav-sync.md](docs/webdav-sync.md).
- **Обновление** — при установке новой версии можно объединить `data.json` из старых каталогов (см. [ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md), раздел «Обновление и базы старых версий»).

## Отличия от upstream

| | [useraitester-creator/win-timer-app-v1](https://github.com/useraitester-creator/win-timer-app-v1) | этот fork |
|--|--|--|
| Пакет | `win_timer_app` | `timerapp_ag` |
| Bitrix24 | базовая интеграция | WebDAV-sync секретов, настройки СПА в UI, расширенный single-instance |
| Linux / Android | нет | `.deb` amd64, APK |
| WebDAV | нет | синхронизация `data.json` |
| Legacy merge | нет | объединение баз старых версий |
| Название продукта | TaskTimer | TaskTimer link B24 |

Синхронизация с upstream: `git fetch upstream` (remote `upstream` → useraitester-creator). Перенос изменений — по фичам, не слепым merge (разная структура пакета).
