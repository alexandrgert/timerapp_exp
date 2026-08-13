# Linux full package matrix (этап 2) — design

**Дата:** 2026-08-13
**Репозиторий:** только [alexandrgert/timerapp_exp](https://github.com/alexandrgert/timerapp_exp) (Experiment)
**Статус:** approved
**Предшественник:** [2026-08-12-linux-extra-packages-design.md](2026-08-12-linux-extra-packages-design.md) (этап 1: deb/rpm/tar/AppImage)

## Цель

Закрыть полную таблицу Linux-форматов в **этом** экспериментальном репо: к уже собранным `.deb` / `.rpm` / `.tar.xz` / `.tgz` / `.AppImage` добавить **Flatpak**, **Snap**, **`.ebuild`**, **`.pisi`**, **`.pet`/`.pup`**, **`.lzm`**.

Локально по-прежнему только `./build_deb.sh`. Остальное — CI / GitHub Releases.

## Решения (зафиксировано)

| Тема | Решение |
|------|---------|
| Подход | **A:** один PyInstaller onedir → staging → отдельные упаковщики в том же Linux CI path |
| Репозиторий | только `timerapp_exp` (не timer-app) |
| Имена артефактов | префикс `timerapp-exp-` |
| Flatpak / Snap ID | `com.timerapp.exp` / snap name `timerapp-exp` |
| Качество | максимально «настоящие» пакеты (валидная структура + метаданные); где нативный tooling недоступен в Ubuntu CI — помечать **experimental**, но всё равно публиковать артефакт |

## Уже есть (этап 1)

- Staging: `packaging/linux/stage_from_pyinstaller.sh`
- Упаковщики: deb / rpm / tarballs / AppImage
- Оркестратор: `build_linux_extra.sh`
- CI job `build-deb` → artifact `linux-packages`

## Новые форматы

### Flatpak — `timerapp-exp-<ver>-x86_64.flatpak`

- Application ID: **`com.timerapp.exp`**
- Manifest под `packaging/linux/flatpak/com.timerapp.exp.yml` (или `.json`)
- Runtime: `org.freedesktop.Platform` / `Sdk` (зафиксировать LTS-ветку при реализации, напр. 24.08)
- Модуль: упаковать уже собранный onedir (не пересобирать Python из исходников в sandbox, если это усложняет CI без выгоды) — например `type: dir` / local sources из `dist/TaskTimer` + desktop/icon
- Сборка: `flatpak-builder` + `flatpak build-bundle` → single-file `.flatpak`
- Finish-args: сеть (Bitrix/WebDAV), X11/Wayland, DBus по необходимости
- CI: установить `flatpak` / `flatpak-builder`, добавить Flathub remote для runtime

### Snap — `timerapp-exp-<ver>-amd64.snap`

- `snapcraft.yaml` name: **`timerapp-exp`**
- База: `core22` или `core24`; app command → wrapper на onedir binary
- Confinement: **strict** + plugs (`network`, `desktop`, `desktop-legacy`, `wayland`, `x11`, `opengl`, `home`, `gsettings`)
- CI: `snapcraft` (destructive mode на ubuntu runner или LXD если доступен)
- Артефакт: `timerapp-exp-<ver>-amd64.snap`, нормализованный из канонического имени snapcraft

### Gentoo ebuild — experimental

- Категория: `app-misc/timerapp-exp`
- Файлы: `packaging/linux/gentoo/app-misc/timerapp-exp/timerapp-exp-<ver>.ebuild` + `metadata.xml`
- Ebuild ставит бинарный tree (из опубликованного `tar.xz` или вложенного distfile), создаёт `/usr/bin/timerapp-exp`
- Артефакт CI: overlay tarball `timerapp-exp-<ver>-gentoo-overlay.tar.xz` **и** копия `.ebuild` как `timerapp-exp-<ver>.ebuild`
- Smoke в CI: `pkgcheck` / синтаксис ebuild при наличии; полный emerge не требуется

### PiSi (`.pisi`) — experimental

- `pspec.xml` / actions для бинарного пакета из staging (`/opt/timerapp_exp`, desktop, icon)
- Сборка: `pisi` tooling если доступен в CI; иначе сформировать `.pisi` как zip/специфичную структуру PiSi (документировать experimental)
- Артефакт: `timerapp-exp-<ver>-x86_64.pisi`

### Puppy `.pet` / `.pup` — experimental

- Структура PET: каталог с файлами под `/` (из staging) + `pet.specs` (name|version|…)
- Упаковка: tar+gzip с расширением `.pet` (классический PET)
- `.pup` — companion/meta при необходимости того же содержимого или slim wrapper; оба имени в релизе, если таблица требует оба
- Артефакты: `timerapp-exp-<ver>-amd64.pet`, `timerapp-exp-<ver>-amd64.pup`

### Slax `.lzm` — experimental

- Модуль: squashfs (или tar→lzm по конвенции Slax) из staging tree
- Инструмент: `mksquashfs` (`squashfs-tools`) в CI
- Артефакт: `timerapp-exp-<ver>-amd64.lzm`

## Архитектура CI

```text
PyInstaller onedir (уже в build-deb)
        │
        ▼
  stage_from_pyinstaller.sh
        │
        ├── этап 1: rpm, tar.xz, tgz, AppImage
        └── этап 2: flatpak, snap, ebuild/overlay, pisi, pet, pup, lzm
```

- Расширить `build_linux_extra.sh` (или `build_linux_extra.sh` + `build_linux_niche.sh`, вызываемый следом) — **один** Linux job, без повторного PyInstaller.
- Artifact `linux-packages` расширить glob’ами всех новых файлов; `if-no-files-found: error` для обязательных форматов.
- Если snap/flatpak нестабильны: fail the job (качество «настоящие») — не молча пропускать; чинить tooling.

## Именование (сводка)

| Формат | Файл |
|--------|------|
| flatpak | `timerapp-exp-<ver>-x86_64.flatpak` |
| snap | `timerapp-exp-<ver>-amd64.snap` (нормализовать из snapcraft output) |
| ebuild | `timerapp-exp-<ver>.ebuild` + `timerapp-exp-<ver>-gentoo-overlay.tar.xz` |
| pisi | `timerapp-exp-<ver>-x86_64.pisi` |
| pet | `timerapp-exp-<ver>-amd64.pet` |
| pup | `timerapp-exp-<ver>-amd64.pup` |
| lzm | `timerapp-exp-<ver>-amd64.lzm` |

## Документация

Обновить README, ИНСТРУКЦИЯ, system-requirements, architecture, agent rule:

- Полная матрица Linux Experiment
- Flatpak ID `com.timerapp.exp`, snap `timerapp-exp`
- Пометка **experimental** у ebuild/pisi/pet/pup/lzm
- Локально только deb; всё остальное — CI

## Критерии приёмки

1. CI Linux job публикует этап-1 **и** этап-2 артефакты с именами выше.
2. Flatpak bundle устанавливается / `flatpak info` на runner (или `flatpak build-bundle` success + `file`/size check).
3. Snap: `unsquashfs -l` / `snap info` на `.snap` без ошибки структуры.
4. ebuild: валидный текстовый ebuild + overlay archive с правильными путями.
5. pisi/pet/pup/lzm: `file` + структурная проверка (наличие desktop/binary paths внутри).
6. Docs согласованы; PR в `main` + push.

## Риски

| Риск | Митигация |
|------|-----------|
| flatpak-builder / snapcraft тяжёлые и хрупкие в GHA | Pin runtime/base; destructive snapcraft; кэш; отдельный step с clear logs |
| PiSi/Puppy tooling нет в Ubuntu | Ручная сборка валидного container format + experimental badge |
| Ограничения Snap strict для desktop-интеграции | Явные plugs + smoke-проверка структуры в CI |
| Размер артефактов / лимиты | Один artifact folder; сжатие где уместно |

## Вне скоупа

- Публикация в Flathub / Snap Store (только файлы в GitHub Releases)
- Сборки для `timer-app` / бренда LinkB24
- Не-amd64

## Открытых вопросов нет

Решения brainstorming 2026-08-13: вся таблица, качество «настоящие», ID Experiment, подход A, только timerapp_exp.
