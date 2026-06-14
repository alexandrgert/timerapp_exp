# TaskTimer link B24

Десктопный таймер задач на Python + [PySide6](https://doc.qt.io/qtforpython/) с интеграцией **Битрикс24**: импорт проектов (СПА) и задач, создание задач на портале, синхронизация завершения.

**Fork** проекта [lukoyanov-aa/win-timer-app-v1](https://github.com/lukoyanov-aa/win-timer-app-v1). От upstream: пакет переименован `win_timer_app` → `timerapp_ag`, добавлена интеграция Bitrix24, Linux `.deb`, single-instance, semver bump при сборке.

Инструкция для пользователей — [`ИНСТРУКЦИЯ.md`](ИНСТРУКЦИЯ.md). Сборка `.exe` — [`README-DISTRIBUTION.txt`](README-DISTRIBUTION.txt).

## Возможности

- Три вида списка: **план на сегодня**, **в работе**, **все задачи**; фильтр по дате учёта времени.
- Таймер по задачам, история интервалов, напоминание «продолжать?», режим **Фокус** (обратный отсчёт).
- Системный трей и плавающий виджет активной задачи.
- **Битрикс24**: импорт проектов/задач, «Открыть в Б24», создание задачи с привязкой к компании, автозавершение на портале.
- Настройки СПА «Реестр проектов» — в UI (**Определить с портала**) или в `ui.bitrix.portal` в `data.json`.

Спецификация модели «план на день»: [`docs/superpowers/specs/2026-06-11-task-views-and-plan-design.md`](docs/superpowers/specs/2026-06-11-task-views-and-plan-design.md).

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

Готовые `.deb` можно прикреплять к [GitHub Releases](https://github.com/alexandrgert/timer-app/releases) этого репозитория.

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
src/timerapp_ag/
  main.py              # точка входа
  env_loader.py        # загрузка .env
  controller.py        # бизнес-логика, план на день, Б24
  main_window.py       # UI
  models.py            # Task, Session
  storage.py           # data.json (AppData / .localdata)
  bitrix.py            # клиент Битрикс24
  bitrix_config.py     # СПА реестра проектов
tests/
docs/superpowers/specs/
```

## Битрикс24

- **Вебхук** — `BITRIX24_HOOK_URL` в `.env` в корне репозитория (или `~/.config/tasktimer/.env` / `%APPDATA%\TaskTimer\.env`).
- **Права вебхука**: `task`, `crm`, `user`.
- **Реестр проектов** — смарт-процесс на портале (по умолчанию entityTypeId 150, «Реестр проектов»); поля исполнителя определяются автоматически или через **Настройки → Определить с портала**.

## Данные

Задачи и настройки — в `data.json` в каталоге приложения Qt (`AppDataLocation`); при недоступности — `.localdata/data.json` в каталоге проекта.

## Отличия от upstream

| | [lukoyanov-aa/win-timer-app-v1](https://github.com/lukoyanov-aa/win-timer-app-v1) | этот fork |
|--|--|--|
| Пакет | `win_timer_app` | `timerapp_ag` |
| Bitrix24 | нет | импорт/создание задач, СПА |
| Linux | нет | `.deb` amd64 |
| Single instance | нет | да |
| Название продукта | TaskTimer | TaskTimer link B24 |
