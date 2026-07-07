# Системные требования TaskTimer Experiment

Минимальные требования для **установленных** сборок (не для разработки из исходников).

Текущая версия в ветке **timerapp_exp**: **0.5.51** (см. [`pyproject.toml`](../pyproject.toml)).  
Стабильные релизы **TaskTimer link B24** — [timer-app](https://github.com/alexandrgert/timer-app/releases).

---

## Сводная таблица

| Платформа | Артефакт | ОС | Процессор | ОЗУ | Диск | Сеть |
|-----------|----------|-----|-----------|-----|------|------|
| **Linux** | `.deb` amd64 | Debian 11+, Ubuntu 20.04+, Mint, Astra и др. с **glibc ≥ 2.31** | x86_64 (64-bit) | 512 МБ | ~200 МБ | для Битрикс24 / WebDAV |
| **Windows** | `.exe` win64 | Windows **10** (64-bit) или **11** | x86_64 (AMD64) | 512 МБ | ~150 МБ | для Битрикс24 / WebDAV |
| **macOS** | `.app` в `.zip` | **macOS 11** Big Sur и новее | Apple Silicon (**arm64**) в релизе; Intel — отдельная сборка | 512 МБ | ~200 МБ | для Битрикс24 / WebDAV |
| **Android** | `.apk` | **Android 10** (API 29) и новее | arm64-v8a, armeabi-v7a | 512 МБ | ~50 МБ | для WebDAV; Битрикс24 — в планах |

**Не поддерживается:** 32-bit Linux/Windows, iOS (в планах), Flatpak/AppImage.

---

## Linux (`.deb` amd64)

### Минимум для работы

| Параметр | Требование |
|----------|------------|
| Архитектура | **amd64** (x86_64) |
| Ядро / libc | glibc **≥ 2.31** (типично Ubuntu 20.04+, Debian 11+) |
| Графика | X11 или Wayland, рабочий стол с системным треем |
| ОЗУ | 512 МБ свободной (рекомендуется 1 ГБ+) |
| Диск | ~200 МБ под программу; данные — отдельно в `~/.local/share/timerapp/` |

Пакет тянет зависимости: OpenGL/EGL, X11, fontconfig, DBus, libtiff (см. `Depends` в `build_deb.sh`).

### WebDAV (Linux)

- Периодическая проверка сервера работает **в фоне** (в том числе при свёрнутом окне в трей).
- Минимальный интервал проверки — **1 минута** (настраивается в UI).

### Сборка (разработчик)

- ОС: Linux **x86_64**
- `dpkg-deb`, Python 3.10+, venv, `requirements-build.txt`
- Команда: `./build_deb.sh` → `dist/timerapp-exp-<версия>-amd64.deb`, запуск: `timerapp-exp`

---

## Windows (`.exe` win64)

### Минимум для работы

| Параметр | Требование |
|----------|------------|
| ОС | **Windows 10** или **11**, только **64-bit** |
| Процессор | x64 (AMD64); ARM Windows **не** поддерживается |
| ОЗУ | 512 МБ (рекомендуется 1 ГБ+) |
| Диск | ~150 МБ под `TaskTimer.exe`; данные в `%LOCALAPPDATA%\timerapp\` |
| Прочее | Python ставить **не нужно** (всё внутри exe) |

Первый запуск exe может занять чуть больше времени (распаковка PyInstaller).

### WebDAV (Windows)

- Периодическая проверка работает при свёрнутом окне в трей.
- Минимальный интервал — **1 минута**.

### Сборка (разработчик)

- ОС: **Windows 10/11** x64
- Python 3.10+, PowerShell, venv, `requirements-build.txt`
- Команда: `.\build_exe.ps1` → `dist\tasktimer-link-b24-<версия>-win64.exe`

---

## macOS (`.app`)

### Минимум для работы

| Параметр | Требование |
|----------|------------|
| ОС | **macOS 11** Big Sur и новее |
| Процессор | Apple Silicon (**arm64**) — сборки [timer-app](https://github.com/alexandrgert/timer-app/releases); Intel (x86_64) — отдельная сборка `./build_macos.sh` на Mac |
| ОЗУ | 512 МБ (рекомендуется 1 ГБ+) |
| Диск | ~200 МБ; данные в `~/Library/Application Support/timerapp/` |

Сборка **не подписана** Apple Developer ID — при первом запуске macOS может потребовать
«Открыть в любом случае» в настройках безопасности (Системные настройки → Конфиденциальность и безопасность).

### WebDAV (macOS)

- Периодическая проверка при работе приложения в фоне (трей).
- Минимальный интервал — **1 минута**.

### Сборка (разработчик)

- ОС: **macOS** (только на Darwin)
- Python 3.10+, venv, `requirements-build.txt`
- Команда: `./build_macos.sh` → `dist/tasktimer-link-b24-<версия>-macos-<arch>.zip`

---

## Android (`.apk`)

### Минимум для работы

| Параметр | Требование |
|----------|------------|
| ОС | **Android 10** (API **29**) и новее |
| ABI | arm64-v8a, armeabi-v7a (типичные телефоны и планшеты) |
| ОЗУ | 512 МБ |
| Диск | ~50 МБ |

### Функциональность (0.5.51 Experiment — desktop)

- Локальный таймер задач, фильтры **Сегодня / В работе / Все**, возобновление завершённых задач.
- **Дневные приоритеты 1–4**, фильтр и массовое применение (десктоп).
- **WebDAV** — синхронизация `data.json` с десктопом; поле `daily_priorities` сохраняется при merge.

### Функциональность (Android, timer-app)

- Локальный таймер задач, фильтры **Сегодня / В работе / Все**, возобновление завершённых задач.
- **WebDAV** — синхронизация `data.json` с десктопом; экран настроек, pull/push, фоновая проверка.
- **Битрикс24** — интеграция на Android в разработке (на десктопе полностью доступна).

### WebDAV (Android)

| Режим | Минимальный интервал проверки |
|-------|-------------------------------|
| Приложение **на экране** | 1 мин (настраивается) |
| **Фон** (WorkManager) | **15 мин** — ограничение Android; интервал ниже автоматически поднимается до 15 |

При изменениях на сервере — уведомление или диалог в приложении (аналог «Позже» на десктопе).

### Сборка (разработчик)

- Linux или macOS с JDK 17, curl, unzip
- Перед сборкой: `python scripts/check_version_sync.py`
- Команда: `./build_apk.sh` → `dist/tasktimer-link-b24-<версия>-android.apk`
- SDK и Gradle подтягиваются в `android/.android-sdk`, `android/.jdk17`

Release APK подписан **debug-ключом** — для публикации в Google Play нужен release keystore.

---

## Общие требования (все платформы)

| Функция | Требование |
|---------|------------|
| **WebDAV** | HTTPS-доступ к серверу (Nextcloud, Яндекс.Диск, корпоративное облако и т.п.); один общий файл `data.json` |
| **Битрикс24** (desktop) | Доступ в интернет, входящий вебхук с правами task, crm, user |
| **Один экземпляр** | Desktop: второй запуск активирует уже открытое окно |
| **Данные** | ~1–50 МБ на типичную базу задач (зависит от истории) |
| **Секреты** | Пароль WebDAV и вебхук Б24 **не** попадают в облако — только локально на каждом устройстве |

---

## Скачивание сборок

Готовые артефакты **Experiment** — [timerapp_exp Releases](https://github.com/alexandrgert/timerapp_exp/releases).  
Полный набор платформ — [timer-app Releases](https://github.com/alexandrgert/timer-app/releases).

| Файл | Платформа |
|------|-----------|
| `timerapp-exp-*-amd64.deb` | Linux (Experiment) |
| `tasktimer-link-b24-*-amd64.deb` | Linux (timer-app) |
| `tasktimer-link-b24-*-win64.exe` | Windows |
| `tasktimer-link-b24-*-macos-arm64.zip` / `*-macos-x86_64.zip` | macOS |
| `tasktimer-link-b24-*-android.apk` | Android |

**Текущая версия Experiment (ветка):** **0.5.51** — Linux `.deb` локально или из CI.

CI (`.github/workflows/ci.yml`) при push в `main` собирает **Linux .deb**, **Windows .exe**, **macOS .zip** и **Android .apk**.

---

## См. также

- [ИНСТРУКЦИЯ.md](../ИНСТРУКЦИЯ.md) — для пользователей
- [architecture-cross-platform.md](architecture-cross-platform.md) — архитектура
- [release-notes-v0.5.51.md](release-notes-v0.5.51.md) — что нового в Experiment 0.5.51
