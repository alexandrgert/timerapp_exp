# GitHub Release v0.11.0 — черновик описания

Экспериментальный релиз **TaskTimer Experiment** ([timerapp_exp](https://github.com/alexandrgert/timerapp_exp)).

Сравнение с **[v0.10.0](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.10.0)**.

## Что нового

- **Полная матрица Linux** из одного PyInstaller onedir в CI: `.deb`, `.rpm`, `.tar.xz`, `.tgz`, `.AppImage`, Flatpak (`com.timerapp.exp`), Snap (`timerapp-exp`, strict), Gentoo ebuild + overlay, PiSi, PET, PUP, Slax LZM
- Локально по-прежнему только `.deb`; extras — CI / этот Release
- ebuild / PiSi / PET / PUP / LZM — **experimental**
- AppImage: pin `appimagetool` 1.9.1 + SHA-256 в CI
- Snap: offline `snap pack` (без Snap Store на runner)

### Проверка обновлений на GitHub (с 0.10.0)

- Desktop: **Параметры → Приложение**; Android: настройки WebDAV.
- Смотрит последний Release репозитория `owner/name` (по умолчанию `alexandrgert/timerapp_exp`; можно указать, например, `alexandrgert/timer-app`).
- Автопроверка опциональна (период 1…30 дней); **«Проверить сейчас»** всегда доступна.
- Только уведомление — пакет сам не ставится. Подробности и примеры — [release-notes-v0.11.0.md](https://github.com/alexandrgert/timerapp_exp/blob/main/docs/release-notes-v0.11.0.md).

Остальное из 0.10.0 без изменений: WebDAV reconnect/лог, экспорт/импорт настроек, поиск, `keep_priority`.

## Установка (Linux amd64)

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.11.0/timerapp-exp-0.11.0-amd64.deb
sudo dpkg -i timerapp-exp-0.11.0-amd64.deb
sudo apt-get install -f
timerapp-exp
```

## Артефакты

| Платформа | Файл |
|-----------|------|
| Linux deb | `timerapp-exp-0.11.0-amd64.deb` |
| Linux rpm | `timerapp-exp-0.11.0-amd64.rpm` |
| Linux tar.xz | `timerapp-exp-0.11.0-linux-amd64.tar.xz` |
| Linux tgz | `timerapp-exp-0.11.0-linux-amd64.tgz` |
| Linux AppImage | `timerapp-exp-0.11.0-x86_64.AppImage` |
| Linux Flatpak | `timerapp-exp-0.11.0-x86_64.flatpak` |
| Linux Snap | `timerapp-exp-0.11.0-amd64.snap` |
| Linux Gentoo (**experimental**) | `timerapp-exp-0.11.0.ebuild`, `timerapp-exp-0.11.0-gentoo-overlay.tar.xz` |
| Linux PiSi (**experimental**) | `timerapp-exp-0.11.0-x86_64.pisi` |
| Linux PET (**experimental**) | `timerapp-exp-0.11.0-amd64.pet` |
| Linux PUP (**experimental**) | `timerapp-exp-0.11.0-amd64.pup` |
| Linux LZM (**experimental**) | `timerapp-exp-0.11.0-amd64.lzm` |
| Android | `timerapp-exp-0.11.0-android.apk` |
| Windows | `timerapp-exp-0.11.0-win64.exe` |
| macOS | `timerapp-exp-0.11.0-macos-arm64.zip` |

## Документация

- [ИНСТРУКЦИЯ.md](https://github.com/alexandrgert/timerapp_exp/blob/main/ИНСТРУКЦИЯ.md)
- [Release notes](https://github.com/alexandrgert/timerapp_exp/blob/main/docs/release-notes-v0.11.0.md)
- [Системные требования](https://github.com/alexandrgert/timerapp_exp/blob/main/docs/system-requirements.md)

> Стабильные сборки всех платформ — [timer-app](https://github.com/alexandrgert/timer-app/releases).
