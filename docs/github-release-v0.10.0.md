Экспериментальный релиз **TaskTimer Experiment** ([timerapp_exp](https://github.com/alexandrgert/timerapp_exp)).

Сравнение с **[v0.7.0](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.7.0)**.

## Что нового

- **WebDAV reconnect** — после восстановления сети отложенный push (debounce + cooldown); если sync занят, push догоняется после idle; на Android UI перечитывает базу после merge
- **Журнал WebDAV («Лог»)** — локальный log операций ↑/↓ задач и ошибок (desktop и Android)
- **Проверка обновлений** — опциональная автопроверка GitHub Releases + «Проверить сейчас»
- **Экспорт / импорт настроек** — JSON с секретами (0600), двойное подтверждение перед импортом, сохранение локального `device_id`
- **Поиск по названию** — поверх вкладки и фильтра приоритетов (эфемерный)
- **«Сохранять приоритет»** (`keep_priority`) — копировать вчерашний приоритет при overnight rollover
- **Merge сессий** — lockstep desktop/Android: union по `session.id`, richer-session с учётом `bitrix_record_id` / `comment`

## Установка (Linux amd64)

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.10.0/timerapp-exp-0.10.0-amd64.deb
sudo dpkg -i timerapp-exp-0.10.0-amd64.deb
sudo apt-get install -f
timerapp-exp
```

## Артефакты

| Платформа | Файл |
|-----------|------|
| Linux | [`timerapp-exp-0.10.0-amd64.deb`](https://github.com/alexandrgert/timerapp_exp/releases/download/v0.10.0/timerapp-exp-0.10.0-amd64.deb) |
| Android | [`timerapp-exp-0.10.0-android.apk`](https://github.com/alexandrgert/timerapp_exp/releases/download/v0.10.0/timerapp-exp-0.10.0-android.apk) |
| Windows | [`timerapp-exp-0.10.0-win64.exe`](https://github.com/alexandrgert/timerapp_exp/releases/download/v0.10.0/timerapp-exp-0.10.0-win64.exe) |
| macOS | [`timerapp-exp-0.10.0-macos-arm64.zip`](https://github.com/alexandrgert/timerapp_exp/releases/download/v0.10.0/timerapp-exp-0.10.0-macos-arm64.zip) |

## Документация

- [ИНСТРУКЦИЯ.md](https://github.com/alexandrgert/timerapp_exp/blob/main/ИНСТРУКЦИЯ.md)
- [Release notes](https://github.com/alexandrgert/timerapp_exp/blob/main/docs/release-notes-v0.10.0.md)
- [Системные требования](https://github.com/alexandrgert/timerapp_exp/blob/main/docs/system-requirements.md)

> Стабильные сборки всех платформ — [timer-app](https://github.com/alexandrgert/timer-app/releases).
