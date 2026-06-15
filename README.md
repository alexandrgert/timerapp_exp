# TaskTimer link B24

Десктопный таймер задач на Python + [PySide6](https://doc.qt.io/qtforpython/) с интеграцией **Битрикс24**: импорт проектов (СПА) и задач, создание задач на портале, синхронизация завершения. **Синхронизация базы задач через WebDAV** (Nextcloud, Яндекс.Диск и др.).

**Fork** проекта [lukoyanov-aa/win-timer-app-v1](https://github.com/lukoyanov-aa/win-timer-app-v1). От upstream: пакет переименован `win_timer_app` → `timerapp_ag`, добавлена интеграция Bitrix24, Linux `.deb`, single-instance, semver bump при сборке.

Инструкция для пользователей — [`ИНСТРУКЦИЯ.md`](ИНСТРУКЦИЯ.md). Сборка `.exe` — [`README-DISTRIBUTION.txt`](README-DISTRIBUTION.txt).

## Возможности

- Три вида списка: **план на сегодня**, **в работе**, **все задачи**; фильтр по дате учёта времени.
- Таймер по задачам, история интервалов, напоминание «продолжать?», режим **Фокус** (обратный отсчёт).
- Системный трей и плавающий виджет активной или приостановленной задачи (скрывается после завершения); щелчок по иконке в трее показывает или скрывает главное окно.
- **Объединение баз** от старых версий — по запросу при обновлении или из меню «Настройки».
- **Битрикс24**: импорт проектов/задач, «Открыть в Б24», создание задачи с привязкой к компании, автозавершение на портале.
- **WebDAV**: синхронизация `data.json` между компьютерами; настройки в UI или `.env`.
- Настройки СПА «Реестр проектов» — в UI (**Определить с портала**) или в `ui.bitrix.portal` в `data.json`.

Спецификация модели «план на день»: [`docs/superpowers/specs/2026-06-11-task-views-and-plan-design.md`](docs/superpowers/specs/2026-06-11-task-views-and-plan-design.md).

Документация: [архитектура](docs/architecture-cross-platform.md) · [схема данных](docs/data-schema.md) · [WebDAV (техн.)](docs/webdav-sync.md) · [релиз 0.4.0](docs/release-notes-v0.4.0.md)

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

## Сборка TaskTimer.exe (Windows)

```powershell
.\build_exe.ps1
```

Результат: `dist\TaskTimer.exe`.

## Сборка .deb (Linux amd64)

Единственный формат дистрибуции для Linux — **Debian-пакет amd64** (не Flatpak).

```bash
./build_deb.sh
```

WebDAV: [`docs/webdav-sync.md`](docs/webdav-sync.md).

Требования: `dpkg-deb`, venv с зависимостями проекта, PyInstaller из `requirements-build.txt`.

Версия — в **`pyproject.toml`**, при сборке **автоматически поднимается** (semver):

| Команда | Когда |
|---------|--------|
| `./build_deb.sh` | мелкие правки → **patch** (0.1.0 → 0.1.1) |
| `BUMP=minor ./build_deb.sh` | новые фичи → **minor** (0.1.0 → 0.2.0) |
| `BUMP=major ./build_deb.sh` | ломающие изменения |
| `NO_BUMP=1 ./build_deb.sh` | пересборка без смены версии |

```bash
chmod +x build_deb.sh
./build_deb.sh
```

Результат: `dist/tasktimer-link-b24-<версия>-amd64.deb`. В меню — «TaskTimer link B24»; версия — в заголовке окна.

Установка:

```bash
sudo dpkg -i dist/tasktimer-link-b24-<версия>-amd64.deb
sudo apt-get install -f
tasktimer-link-b24
```

Upgrade/downgrade: более новая версия ставится поверх старой; downgrade блокируется (`preinst`) — сначала `sudo apt remove tasktimer-link-b24`.

Ручной bump без сборки: `python scripts/bump_version.py minor`

### Releases

Готовые `.deb` публикуются в [GitHub Releases](https://github.com/alexandrgert/timer-app/releases).

**Последний релиз:** [v0.4.0](https://github.com/alexandrgert/timer-app/releases/tag/v0.4.0) — [текст для пользователей](docs/release-notes-v0.4.0.md)

Скачать пакет (Linux amd64):

https://github.com/alexandrgert/timer-app/releases/download/v0.4.0/tasktimer-link-b24-0.4.0-amd64.deb

```bash
wget https://github.com/alexandrgert/timer-app/releases/download/v0.4.0/tasktimer-link-b24-0.4.0-amd64.deb
sudo dpkg -i tasktimer-link-b24-0.4.0-amd64.deb
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

## Данные

- **Задачи и UI** — `data.json` в каталоге данных приложения (см. `platform_paths.py` / [data-schema](docs/data-schema.md)).
- **Секреты** (вебхук, пароль WebDAV) — `~/.config/tasktimer/` (`bitrix.json`, `webdav.json`).
- **WebDAV** — опциональная синхронизация `data.json`; см. [ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md) и [webdav-sync.md](docs/webdav-sync.md).
- **Обновление** — при установке новой версии можно объединить `data.json` из старых каталогов (см. [ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md), раздел «Обновление и базы старых версий»).

## Отличия от upstream

| | [lukoyanov-aa/win-timer-app-v1](https://github.com/lukoyanov-aa/win-timer-app-v1) | этот fork |
|--|--|--|
| Пакет | `win_timer_app` | `timerapp_ag` |
| Bitrix24 | нет | импорт/создание задач, СПА |
| Linux | нет | `.deb` amd64 |
| Single instance | нет | да |
| Название продукта | TaskTimer | TaskTimer link B24 |
