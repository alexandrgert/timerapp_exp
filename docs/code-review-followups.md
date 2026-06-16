# Рекомендации по доработкам (code review)

Документ фиксирует принятые исправления и варианты для следующих итераций.

## Уже исправлено (v0.4.x)

| # | Проблема | Решение |
|---|----------|---------|
| 2 | «Нет» в ручном legacy merge отключало startup-prompt | `record_decline_on_cancel` только при старте |
| 4 | Preview не показывал обогащение существующих задач | `enriched_titles` в диалоге |
| 4+ | Счётчики, ui diff, «Показать подробности» | summary + `setDetailedText` в QMessageBox |
| 3+ | WebDAV shutdown upload-only + уведомление при конфликте | `shutdown_upload_only`, `pending_notice` |
| 5 | `discover_data_files` подхватывал лишний Qt-путь | `discover_legacy_data_files()` без Qt fallback |
| 6 | `quit()` из signal handler | `QTimer.singleShot(0, …)` в event loop |
| 7 | Release notes завышали гарантии | Уточнены SIGTERM vs `kill -9` |
| — | Падение при битом `.bak` | `_load_from_rolling_backup()` с try/except |

---

## 3. WebDAV при выходе меняет локальную базу

**Реализовано:**

- Настройка **«При выходе только отправить локальную копию (без слияния с облаком)»** (`shutdown_upload_only`, по умолчанию выкл.).
- Режим merge при выходе (по умолчанию): pull-before-push как раньше.
- При конфликте на выходе — `pending_notice` в `webdav.json`, показ balloon при следующем запуске.

**Дальше (не реализовано):**

- **Отложенный push** — при конфликте на shutdown сохранять копию в `backups/webdav-conflict` и не upload до ручного разрешения.
- **Версионирование на сервере** — `data-YYYYMMDD.json` + UI выбора версии.

---

## 4. Merge preview

**Реализовано:** счётчики «+N новых задач» / «+M сессий», diff `ui`, «Показать подробности…» через `QMessageBox.setDetailedText`.

---

## 5. Обнаружение legacy-баз (дальнейшее улучшение)

**Сделано:** legacy merge и consolidate используют только `data_share_roots`, без Qt `AppDataLocation`.

**Дальше:**

- Явный whitelist имён каталогов (`TaskTimer*`, `TaskTimer link B24*`).
- Игнор каталогов с `schema_version` / marker «уже merged» в legacy-файле.
- Перенос старых каталогов в `archive/` после успешного merge (с подтверждением).

---

## Прочие рекомендации

- **Тесты shutdown:** покрыть `run_shutdown_backup` (save + backup + mock WebDAV).
- **`task_richer`:** при равном числе сессий сравнивать `ended_at` / длительность, не только `created_at`.
- **Android MVP** (локально): atomic save, полный `ui` JSON, release keystore — перед коммитом в main.
- **CI:** job `build-apk` после стабилизации Android-ветки.
