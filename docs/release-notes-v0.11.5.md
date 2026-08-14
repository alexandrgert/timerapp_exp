# TaskTimer Experiment — версия 0.11.5

**Desktop: проверка обновлений в «О программе» · Android: постоянная подпись APK в CI**

Экспериментальный форк: [alexandrgert/timerapp_exp](https://github.com/alexandrgert/timerapp_exp).  
База сравнения: **[v0.11.1](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.11.1)** (промежуточные локальные сборки 0.11.2–0.11.4 не выходили на GitHub).

## Что нового

### Desktop

- Кнопка **«Проверить сейчас»** в окне **«О программе»** (меню и трей) — та же ручная проверка GitHub Releases, что на вкладке **Настройки → Приложение**.
- Исправлен невидимый статус после «Проверить сейчас» в **Настройках** (метка оставалась с нулевой высотой).

### Android — постоянный release keystore в CI

Раньше GitHub Actions при отсутствии `android/keystore/` **генерировал новый ключ на каждую сборку**.  
Android сравнивает подпись при обновлении: другой ключ → установка «поверх» невозможна.

**С 0.11.5** CI всегда подписывает APK **одним и тем же** release keystore из [GitHub Secrets](https://github.com/alexandrgert/timerapp_exp/settings/secrets/actions). Новый ключ в CI больше не создаётся.

---

## Android: подпись APK — подробно

### Зачем это нужно

У Android-пакета `com.timerapp.exp` есть **цифровая подпись** (как «печать» сборки). При обновлении система проверяет:

| Ситуация | Поведение |
|----------|-----------|
| Тот же ключ, та же `applicationId` | APK ставится **поверх** — данные и WebDAV на устройстве сохраняются |
| Другой ключ, та же `applicationId` | Ошибка вроде **«конфликтует с другим пакетом»** / *App not installed* |
| Другой `applicationId` | Это другое приложение; параллельная установка возможна |

Experiment с **v0.11.0–0.11.1** и ранними CI-сборками мог попадать во вторую строку: каждый run CI мог подписать APK **новым** keystore.

### Что изменилось в 0.11.5

1. В репозитории задан **постоянный** `tasktimer-release.jks` (в git **не** хранится — только в Secrets).
2. Job `build-apk` в CI перед сборкой:
   - декодирует `ANDROID_KEYSTORE_BASE64` → `android/keystore/tasktimer-release.jks`;
   - создаёт `android/keystore.properties` через `scripts/write_android_keystore_from_env.py`.
3. `build_apk.sh` в CI **не генерирует** ключ: если secrets не заданы — сборка падает с понятной ошибкой.

**Secrets** (Settings → Secrets and variables → Actions):

| Secret | Содержимое |
|--------|------------|
| `ANDROID_KEYSTORE_BASE64` | файл `.jks` в base64 (без переносов строк) |
| `ANDROID_KEYSTORE_PASSWORD` | пароль хранилища |
| `ANDROID_KEY_ALIAS` | alias ключа (например `tasktimer`) |
| `ANDROID_KEY_PASSWORD` | пароль ключа |

Локальная sideload-сборка (`./build_apk.sh` **вне CI**) по-прежнему может создать **свой** keystore из `keystore.properties.example` — это **другой** ключ, не совпадающий с Releases.

---

## Примеры для пользователя Android

### Обычное обновление (APK из GitHub Releases ≥ 0.11.5)

1. Скачайте `timerapp-exp-0.11.5-android.apk` из [Releases](https://github.com/alexandrgert/timerapp_exp/releases).
2. Откройте файл на телефоне или через ADB:

```bash
adb install -r timerapp-exp-0.11.5-android.apk
```

Флаг `-r` — replace (обновление поверх). Задачи, WebDAV и настройки на устройстве **остаются**.

3. Следующие релизы (0.11.6, 0.12.0, …) ставятся так же — **без удаления**.

### Уже стоит старый APK с «чужой» подписью

**Симптомы:** при установке нового APK из Releases:

- «Приложение не установлено»;
- «Не удалось установить» / *App not installed*;
- «**Конфликтует с другим пакетом**» (типично для русской локали).

**Причина:** на устройстве установлен Experiment, подписанный **другим** ключом (ранний CI, локальная сборка `./build_apk.sh`, сторонний APK).

**Один раз** нужна переустановка:

1. **Синхронизируйте WebDAV** (или экспорт данных), если база важна — локальный `data.json` на телефоне удалится вместе с приложением.
2. Удалите приложение: **Настройки → Приложения → TaskTimer Experiment → Удалить**  
   или:

```bash
adb uninstall com.timerapp.exp
```

3. Установите APK из текущего Release **без** `-r` (чистая установка):

```bash
adb install timerapp-exp-0.11.5-android.apk
```

4. Снова настройте WebDAV / импорт при необходимости.
5. **Дальше** — только обновления поверх, как в первом примере.

> Если WebDAV уже настроен на других устройствах, после чистой установки достаточно включить синхронизацию и **«Скачать и объединить»** на десктопе или дождаться pull на телефоне.

### Как понять, что подпись «та же»

Сравнить SHA-256 сертификата двух APK (на ПК с Android SDK):

```bash
# APK из GitHub Release
apksigner verify --print-certs timerapp-exp-0.11.5-android.apk | grep -A1 "Signer #1"

# APK, уже установленный на телефоне (нужен root или debuggable build — проще сравнить через установку)
adb shell pm path com.timerapp.exp
adb pull /data/app/.../base.apk old.apk
apksigner verify --print-certs old.apk | grep -A1 "Signer #1"
```

Если строка **certificate SHA-256** совпадает — обновление поверх сработает.

---

## Примеры для сопровождения CI (maintainers)

### Загрузить keystore в GitHub Secrets (однократно)

```bash
# 1. Закодировать .jks (одна строка base64, без переносов)
base64 -w0 android/keystore/tasktimer-release.jks | pbcopy   # macOS
base64 -w0 android/keystore/tasktimer-release.jks | xclip    # Linux

# 2. В GitHub: Settings → Secrets → New repository secret
#    ANDROID_KEYSTORE_BASE64 = вставить буфер обмена
#    ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD — как в keystore.properties
```

Проверка локально (без commit секретов):

```bash
export ANDROID_KEYSTORE_PASSWORD='***'
export ANDROID_KEY_ALIAS='tasktimer'
export ANDROID_KEY_PASSWORD='***'
python3 scripts/write_android_keystore_from_env.py
# → android/keystore.properties (файл в .gitignore)
```

### Что будет, если secrets пропали

CI job `build-apk` завершится на шаге **Restore Android release keystore**:

```text
Missing Android signing secrets (ANDROID_KEYSTORE_BASE64, ...)
```

или в `build_apk.sh`:

```text
CI: нет android/keystore.properties + tasktimer-release.jks.
Ожидаются secrets ANDROID_KEYSTORE_BASE64 / ...
```

APK **не** соберётся с новым случайным ключом — это намеренно.

---

## Сборки

Та же матрица, что в [v0.11.0](release-notes-v0.11.0.md), с префиксом `timerapp-exp-0.11.5-*`.

**Linux amd64 (.deb):**

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.11.5/timerapp-exp-0.11.5-amd64.deb
sudo dpkg -i timerapp-exp-0.11.5-amd64.deb
sudo apt-get install -f
timerapp-exp
```

**Android:**

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.11.5/timerapp-exp-0.11.5-android.apk
adb install -r timerapp-exp-0.11.5-android.apk
```

Полный список артефактов — на странице [Release v0.11.5](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.11.5).

---

## Связанные документы

- [ИНСТРУКЦИЯ.md](../ИНСТРУКЦИЯ.md) — раздел «Android», обновление APK
- [system-requirements.md](system-requirements.md) — сборка Android
- Предыдущий релиз: [v0.11.1](release-notes-v0.11.1.md)
