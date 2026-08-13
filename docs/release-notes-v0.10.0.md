# TaskTimer Experiment — версия 0.10.0

**WebDAV reconnect и журнал, проверка обновлений, экспорт настроек, поиск и keep_priority**

Экспериментальный форк: [alexandrgert/timerapp_exp](https://github.com/alexandrgert/timerapp_exp).  
База сравнения: **[v0.7.0](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.7.0)** (последний опубликованный GitHub Release).

> Стабильная ветка продукта **TaskTimer link B24** — [alexandrgert/timer-app](https://github.com/alexandrgert/timer-app).  
> Здесь — песочница для UX и модели данных; пакеты называются `timerapp-exp-*`.

---

## Что нового

### WebDAV: выгрузка после восстановления сети

- При **offline → online** (если WebDAV включён и настроен) приложение само запускает **push** после короткой задержки (~2.5 с) и с cooldown (~60 с).
- Если в этот момент уже идёт другая синхронизация, push **не теряется**: откладывается и стартует после освобождения.
- Ошибка reconnect-push — уведомление (tray на desktop / notification на Android). Успех — без лишнего шума.
- На Android после merge на диске UI **перечитывает** `data.json`, чтобы не затереть свежие данные старым состоянием в памяти.

### WebDAV: журнал операций («Лог»)

- Локальный `webdav-sync.log` (JSONL, до ~200 записей; **не** в облаке).
- Кнопка **«Лог»** в настройках WebDAV (desktop и Android): дата/время, операция, ↑ отправлено / ↓ скачано задач, OK или текст ошибки.

### Проверка обновлений на GitHub

- Вкладка **«Приложение»** (desktop) / блок в настройках WebDAV (Android).
- Опциональная автопроверка релизов репозитория (по умолчанию `alexandrgert/timerapp_exp`), период 1…30 дней.
- Кнопка **«Проверить сейчас»** доступна всегда; автозапуск только при включённом чекбоксе и истекшем периоде.

### Экспорт / импорт настроек

- Выгрузка локальных настроек (WebDAV, Bitrix webhook/portal на desktop, prefs приложения) в JSON формата `timerapp-settings`.
- Файл с секретами пишется с правами **0600**.
- Импорт: сначала разбор файла, затем **два подтверждения** перезаписи; локальный `device_id` WebDAV сохраняется.
- Worklog-поля portal-конфига при экспорте с desktop **не сбрасываются** в дефолты.

### Поиск по названию

- Поле **«Поиск»** рядом с датой (desktop и Android): фильтр текущего списка поверх вкладки и приоритетов.
- Состояние поиска **эфемерное** (не в `data.json` / WebDAV); сброс при смене вкладки.

### «Сохранять приоритет» (`keep_priority`)

- В диалоге задачи / назначения приоритета: если включено, overnight rollover **копирует вчерашний приоритет на сегодня**.
- По умолчанию выключено (как раньше — приоритет на новый день не переносится).
- Поле в схеме `data.json` (см. [data-schema.md](data-schema.md)).

### Merge сессий WebDAV (lockstep desktop ↔ Android)

- При конфликте одного `session.id`: закрытая сессия → большая длительность → meta (`bitrix_record_id`, непустой `comment`) → иначе candidate.
- Union сессий по `session.id`; одинаковое правило на desktop и Android (фикстуры lockstep + тесты).

---

## Сборки

| Платформа | Файл |
|-----------|------|
| Linux amd64 | `timerapp-exp-0.10.0-amd64.deb` |
| Linux rpm | `timerapp-exp-0.10.0-amd64.rpm` |
| Linux tar.xz | `timerapp-exp-0.10.0-linux-amd64.tar.xz` |
| Linux tgz | `timerapp-exp-0.10.0-linux-amd64.tgz` |
| Linux AppImage | `timerapp-exp-0.10.0-x86_64.AppImage` |
| Android 10+ | `timerapp-exp-0.10.0-android.apk` |
| Windows | `timerapp-exp-0.10.0-win64.exe` |
| macOS | `timerapp-exp-0.10.0-macos-arm64.zip` |

**Linux:**

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.10.0/timerapp-exp-0.10.0-amd64.deb
sudo dpkg -i timerapp-exp-0.10.0-amd64.deb
sudo apt-get install -f
timerapp-exp
```

**Android:** установите APK поверх текущей сборки Experiment (та же подпись) — данные и WebDAV сохранятся.

---

## Коммиты с v0.7.0

| Коммит | Описание |
|--------|----------|
| `0b90583` | test: lockstep merge prefers session bitrix/comment meta |
| `530e00e` | fix(merge): prefer session bitrix/comment when durations tie |
| `e16631c` | fix(android): align session merge tie-break with desktop |
| `4752d94` | docs: describe session union merge for WebDAV |
| `0333ca1` | feat: WebDAV reconnect, sync log, updates and settings I/O (v0.10.0) |

---

## Документация

- [ИНСТРУКЦИЯ.md](../ИНСТРУКЦИЯ.md)
- [WebDAV (техн.)](webdav-sync.md)
- [Схема данных](data-schema.md)
- [Системные требования](system-requirements.md)

Предыдущий релиз: [v0.7.0](release-notes-v0.7.0.md).
