# Системные требования TaskTimer link B24

Минимальные требования для **установленных** сборок (не для разработки из исходников).

Текущая версия продукта: **0.4.4** (см. [`pyproject.toml`](../pyproject.toml)).

---

## Сводная таблица

| Платформа | Артефакт | ОС | Процессор | ОЗУ | Диск | Сеть |
|-----------|----------|-----|-----------|-----|------|------|
| **Linux** | `.deb` amd64 | Debian 11+, Ubuntu 20.04+, Mint, Astra и др. с **glibc ≥ 2.31** | x86_64 (64-bit) | 512 МБ | ~200 МБ | для Битрикс24 / WebDAV |
| **Windows** | `.exe` win64 | Windows **10** (64-bit) или **11** | x86_64 (AMD64) | 512 МБ | ~150 МБ | для Битрикс24 / WebDAV |
| **macOS** | `.app` в `.zip` | **macOS 11** Big Sur и новее | Intel **или** Apple Silicon (arm64) | 512 МБ | ~200 МБ | для Битрикс24 / WebDAV |
| **Android** | `.apk` | **Android 10** (API 29) и новее | arm64-v8a, armeabi-v7a | 512 МБ | ~50 МБ | для Битрикс24 / WebDAV (план) |

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

### Сборка (разработчик)

- ОС: Linux **x86_64**
- `dpkg-deb`, Python 3.10+, venv, `requirements-build.txt`
- Команда: `./build_deb.sh` → `dist/tasktimer-link-b24-<версия>-amd64.deb`

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
| Процессор | Intel (x86_64) **или** Apple Silicon (arm64) — скачивайте сборку под свою архитектуру |
| ОЗУ | 512 МБ (рекомендуется 1 ГБ+) |
| Диск | ~200 МБ; данные в `~/Library/Application Support/timerapp/` |

Сборка **не подписана** Apple Developer ID — при первом запуске macOS может потребовать
«Открыть в любом случае» в настройках безопасности (Системные настройки → Конфиденциальность и безопасность).

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

MVP: локальный таймер задач; паритет с desktop (WebDAV, Битрикс24) — в разработке.

### Сборка (разработчик)

- Linux или macOS с JDK 17, curl, unzip
- Команда: `./build_apk.sh` → `dist/tasktimer-link-b24-<версия>-android.apk`
- SDK и Gradle подтягиваются в `android/.android-sdk`, `android/.jdk17`

Release APK сейчас подписан **debug-ключом** — для публикации в Google Play нужен release keystore.

---

## Общие требования (все desktop-платформы)

| Функция | Требование |
|---------|------------|
| **Битрикс24** | Доступ в интернет, входящий вебхук с правами task, crm, user |
| **WebDAV** | HTTPS-доступ к серверу (Nextcloud, корпоративное облако и т.п.) |
| **Один экземпляр** | Desktop: второй запуск активирует уже открытое окно |
| **Данные** | ~1–50 МБ на типичную базу задач (зависит от истории) |

---

## Скачивание сборок

Готовые артефакты — [GitHub Releases](https://github.com/alexandrgert/timer-app/releases).

| Файл | Платформа |
|------|-----------|
| `tasktimer-link-b24-*-amd64.deb` | Linux |
| `tasktimer-link-b24-*-win64.exe` | Windows |
| `tasktimer-link-b24-*-macos-arm64.zip` / `*-macos-x86_64.zip` | macOS |
| `tasktimer-link-b24-*-android.apk` | Android |

CI (`.github/workflows/ci.yml`) автоматически собирает **Linux .deb**, **Windows .exe** и **macOS .zip** при push в `main`.

---

## См. также

- [ИНСТРУКЦИЯ.md](../ИНСТРУКЦИЯ.md) — для пользователей
- [architecture-cross-platform.md](architecture-cross-platform.md) — архитектура
- [release-notes-v0.4.4.md](release-notes-v0.4.4.md) — что нового в релизе
