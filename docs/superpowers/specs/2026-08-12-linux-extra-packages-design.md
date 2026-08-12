# Linux extra packages (этап 1) — design

**Дата:** 2026-08-12  
**Репозиторий:** [alexandrgert/timerapp_exp](https://github.com/alexandrgert/timerapp_exp)  
**Статус:** draft for review

## Цель

Расширить Linux-дистрибуцию Experiment: помимо `.deb` публиковать в CI / GitHub Releases **`.rpm`**, **`.tar.xz`**, **`.tgz`**, **`.AppImage`**. Локально по-прежнему собирается только `.deb`.

## Вне скоупа (этап 2+)

- Flatpak (`com.timerapp.*`)
- Snap
- `.ebuild`, `.pisi`, `.pet`/`.pup`, `.lzm`
- Не-amd64 архитектуры

## Решения (зафиксировано)

| Тема | Решение |
|------|---------|
| Подход | **A:** один PyInstaller onedir → несколько упаковщиков |
| Имена | префикс `timerapp-exp-` (как текущий `.deb`) |
| Flatpak/Snap | следующий этап |
| Локально | только `./build_deb.sh` |
| CI | amd64 Linux: deb + rpm + tar.xz + tgz + AppImage |

## Текущее состояние

- [`build_deb.sh`](../../build_deb.sh): bump версии → PyInstaller `TaskTimer-linux.spec` → дерево `/opt/timerapp_exp` + wrapper `usr/bin/timerapp-exp` + `.desktop` + SVG → `dpkg-deb`.
- CI (`.github/workflows/ci.yml`): job `build-deb` с `ALLOW_NO_BUMP=1 NO_BUMP=1`.
- Документы сейчас утверждают «только `.deb`», Flatpak/AppImage не используются — нужно обновить после внедрения.

## Архитектура упаковки

```text
PyInstaller onedir (dist/TaskTimer/)
        │
        ▼
  staging root (общий layout)
  /opt/timerapp_exp/...
  /usr/bin/timerapp-exp
  /usr/share/applications/timerapp-exp.desktop
  /usr/share/icons/.../timerapp-exp.svg
        │
        ├──► .deb      (dpkg-deb)     — локально + CI
        ├──► .rpm      (fpm или rpmbuild) — CI
        ├──► .tar.xz   (tar -C staging)   — CI
        ├──► .tgz      (tar.gz)           — CI
        └──► .AppImage (linuxdeploy / appimagetool) — CI
```

### Staging

Вынести из `build_deb.sh` общую функцию/скрипт (например `packaging/linux/stage_from_pyinstaller.sh` или Python-хелпер), который:

1. Принимает путь к `dist/TaskTimer`, `VERSION`, `INSTALL_PREFIX` (`/opt/timerapp_exp`), `BIN_NAME` (`timerapp-exp`).
2. Собирает filesystem tree в temp/staging dir.
3. Пишет `VERSION`, launcher, desktop, icon (как сейчас в `build_deb.sh`).

`build_deb.sh` вызывает staging → `dpkg-deb`.  
Новый `build_linux_packages.sh` (или расширение CI) вызывает тот же staging → остальные форматы.  
Локальный `build_deb.sh` **не** обязан собирать rpm/AppImage (чтобы не требовать fpm/appimagetool у разработчика).

### Имена артефактов

| Формат | Имя файла |
|--------|-----------|
| deb | `timerapp-exp-<ver>-amd64.deb` |
| rpm | `timerapp-exp-<ver>-amd64.rpm` |
| tar.xz | `timerapp-exp-<ver>-linux-amd64.tar.xz` |
| tgz | `timerapp-exp-<ver>-linux-amd64.tgz` |
| AppImage | `timerapp-exp-<ver>-x86_64.AppImage` |

Версия — из `pyproject.toml` (в CI без bump, как сейчас).

### Содержимое tar.xz / tgz

- Корень архива: содержимое staging **относительно `/`** (т.е. `opt/…`, `usr/…`), чтобы распаковка в `/` давала установку.
- Рядом в корне архива (или `INSTALL.txt`): краткая инструкция `sudo tar -C / -xvf …` и как удалить.
- Не включать control-файлы Debian/RPM.

### RPM

- Prefer **`fpm`** в CI (ruby gem или prebuilt) из того же staging: `-s dir -t rpm`, depends по аналогии с deb (`Depends` → `Requires` best-effort).
- Альтернатива: `rpmbuild` spec — только если fpm окажется проблемным в Actions.
- Пакет: amd64 / x86_64; имя `timerapp-exp`.

### AppImage

- База: тот же onedir + `.desktop` + icon.
- Инструменты: `linuxdeploy` + `appimagetool` (или один `linuxdeploy` с plugin), скачиваются в CI.
- AppDir layout: `usr/bin/TaskTimer` (или symlink), desktop `Exec=`, `Icon=`.
- Артефакт executable `.AppImage`, без обязательной подписи на этапе 1 (можно unsigned; в docs указать).

## CI

Варианты реализации (выбрать при плане; предпочтение — меньше дублирования PyInstaller):

1. **Расширить `build-deb`:** после PyInstaller/deb собрать rpm/tar/AppImage в том же job, upload несколько artifacts или один `linux-packages` artifact folder.
2. **Отдельный job `build-linux-extra`:** `needs: build-deb`, скачать deb-артефакт **недостаточно** (нет onedir) — лучше `needs: test` и либо re-run PyInstaller, либо upload intermediate `pyinstaller-onedir` artifact из `build-deb`.

Рекомендация для плана: в `build-deb` после PyInstaller сохранить onedir как artifact **или** сразу упаковать все форматы в одном job (проще для v1).

Jobs win/mac/apk без изменений.

## Документация

Обновить:

- [`docs/system-requirements.md`](../system-requirements.md) — список Linux-артефактов; убрать «Flatpak/AppImage не поддерживается» → AppImage поддерживается; Flatpak/Snap — «в планах».
- [`docs/architecture-cross-platform.md`](../architecture-cross-platform.md) — Linux не только deb.
- [`README.md`](../../README.md), [`ИНСТРУКЦИЯ.md`](../../ИНСТРУКЦИЯ.md) — таблица загрузок.
- Release notes следующего релиза — перечислить новые форматы.

Правило версии (`.cursor/rules`): локально «собери» = только deb; apk по явной просьбе; новые linux-форматы — **только CI**, не предлагать локальную сборку rpm/AppImage по умолчанию.

## Критерии приёмки этапа 1

1. Push в `main` → CI собирает 5 Linux-файлов с именами выше.
2. Артефакты скачиваются с Actions / можно приложить к GitHub Release.
3. `.deb` поведение не регрессирует (установка `timerapp-exp` как сейчас).
4. `.tar.xz`/`.tgz` распаковываются в `/` и дают тот же launcher (smoke: наличие бинарника в архиве).
5. `.AppImage` — файл executable, `--appimage-extract` или `--help`/запуск в CI headless smoke по возможности.
6. `.rpm` — `rpm -qp` / `file` показывает RPM; установка на Fedora не обязательна в CI ubuntu (достаточно валидного пакета).
7. Docs согласованы с новой матрицей.

## Риски

| Риск | Митигация |
|------|-----------|
| fpm/appimagetool недоступны или ломают Qt libs | Pin URL/версий инструментов; fallback docs «best-effort» |
| AppImage раздувается / не стартует без FUSE | Использовать type-2 AppImage; документировать `./….AppImage` |
| Дублирование PyInstaller в CI | Один job / shared artifact onedir |
| Alien-качество RPM | Не использовать alien; staging → fpm |

## Открытых вопросов нет

Все продуктовые решения этапа 1 закрыты в brainstorming (2026-08-12).
