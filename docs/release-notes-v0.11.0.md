# TaskTimer Experiment — версия 0.11.0

**Полная матрица Linux-пакетов в CI и GitHub Releases**

Экспериментальный форк: [alexandrgert/timerapp_exp](https://github.com/alexandrgert/timerapp_exp).  
База сравнения: **[v0.10.0](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.10.0)** (последний опубликованный GitHub Release).

> Стабильная ветка продукта **TaskTimer link B24** — [alexandrgert/timer-app](https://github.com/alexandrgert/timer-app).  
> Здесь — песочница для UX и модели данных; пакеты называются `timerapp-exp-*`.

---

## Что нового

### Полная матрица Linux (Approach A)

Из **одного** PyInstaller onedir в CI собираются:

| Формат | Артефакт | Примечание |
|--------|----------|------------|
| deb | `timerapp-exp-0.11.0-amd64.deb` | как раньше; локально — только он |
| rpm | `timerapp-exp-0.11.0-amd64.rpm` | fpm |
| tar.xz / tgz | `…-linux-amd64.tar.xz` / `.tgz` | portable tree |
| AppImage | `…-x86_64.AppImage` | appimagetool **1.9.1** + SHA-256 |
| Flatpak | `…-x86_64.flatpak` | ID **`com.timerapp.exp`**, runtime 24.08 |
| Snap | `…-amd64.snap` | имя **`timerapp-exp`**, strict; offline `snap pack` |
| Gentoo | `.ebuild` + `…-gentoo-overlay.tar.xz` | **experimental** |
| PiSi | `…-x86_64.pisi` | **experimental** |
| Puppy PET / PUP | `…-amd64.pet` / `.pup` | **experimental** |
| Slax LZM | `…-amd64.lzm` | **experimental** |

Локально по-прежнему только `./build_deb.sh`. Остальное — CI / Releases.

### Прочее с v0.10.0

Продуктовые фичи 0.10.0 (WebDAV reconnect/лог, проверка обновлений, экспорт настроек, поиск, `keep_priority`, merge сессий) без изменений поведения — см. [release-notes-v0.10.0.md](release-notes-v0.10.0.md).

---

## Сборки

| Платформа | Файл |
|-----------|------|
| Linux amd64 (.deb) | `timerapp-exp-0.11.0-amd64.deb` |
| Linux amd64 (.rpm) | `timerapp-exp-0.11.0-amd64.rpm` |
| Linux amd64 (tar.xz) | `timerapp-exp-0.11.0-linux-amd64.tar.xz` |
| Linux amd64 (.tgz) | `timerapp-exp-0.11.0-linux-amd64.tgz` |
| Linux amd64 (AppImage) | `timerapp-exp-0.11.0-x86_64.AppImage` |
| Linux amd64 (Flatpak) | `timerapp-exp-0.11.0-x86_64.flatpak` |
| Linux amd64 (Snap) | `timerapp-exp-0.11.0-amd64.snap` |
| Linux Gentoo (**experimental**) | `timerapp-exp-0.11.0.ebuild`, `timerapp-exp-0.11.0-gentoo-overlay.tar.xz` |
| Linux PiSi (**experimental**) | `timerapp-exp-0.11.0-x86_64.pisi` |
| Linux PET (**experimental**) | `timerapp-exp-0.11.0-amd64.pet` |
| Linux PUP (**experimental**) | `timerapp-exp-0.11.0-amd64.pup` |
| Linux LZM (**experimental**) | `timerapp-exp-0.11.0-amd64.lzm` |
| Android 10+ | `timerapp-exp-0.11.0-android.apk` |
| Windows | `timerapp-exp-0.11.0-win64.exe` |
| macOS | `timerapp-exp-0.11.0-macos-arm64.zip` |

**Linux (.deb):**

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.11.0/timerapp-exp-0.11.0-amd64.deb
sudo dpkg -i timerapp-exp-0.11.0-amd64.deb
sudo apt-get install -f
timerapp-exp
```

**Flatpak / Snap (кратко):**

```bash
flatpak install --user timerapp-exp-0.11.0-x86_64.flatpak
sudo snap install timerapp-exp-0.11.0-amd64.snap --dangerous
```

**Android:** установите APK поверх текущей сборки Experiment (та же подпись) — данные и WebDAV сохранятся.

---

## Документация

- [ИНСТРУКЦИЯ.md](../ИНСТРУКЦИЯ.md)
- [Системные требования](system-requirements.md)
- [Архитектура](architecture-cross-platform.md)
- [Спека матрицы](superpowers/specs/2026-08-13-linux-full-matrix-design.md)

Предыдущий релиз: [v0.10.0](release-notes-v0.10.0.md).
