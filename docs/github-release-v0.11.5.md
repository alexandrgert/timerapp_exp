# GitHub Release v0.11.5 — черновик описания

Экспериментальный релиз **TaskTimer Experiment** ([timerapp_exp](https://github.com/alexandrgert/timerapp_exp)).

Сравнение с **[v0.11.1](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.11.1)**.

## Что нового

- **«О программе»** — кнопка «Проверить сейчас» (GitHub Releases)
- **Настройки** — исправлен невидимый статус проверки обновлений
- **Android** — APK из CI подписывается **постоянным** release keystore (GitHub Secrets); обновления с Releases ставятся поверх без смены ключа

## Android: обновление APK

**Обычный случай** — скачайте `timerapp-exp-0.11.5-android.apk` и установите поверх текущей Experiment.

**Если система пишет «конфликтует с другим пакетом»** — на устройстве стоит сборка с другой подписью (ранний CI). Один раз: синхронизируйте WebDAV → удалите приложение → установите APK из этого Release → снова WebDAV. Дальше — только поверх.

Подробно, с примерами `adb install` и настройкой secrets: **[release-notes-v0.11.5.md](https://github.com/alexandrgert/timerapp_exp/blob/main/docs/release-notes-v0.11.5.md)**.

## Установка (Linux amd64)

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.11.5/timerapp-exp-0.11.5-amd64.deb
sudo dpkg -i timerapp-exp-0.11.5-amd64.deb
sudo apt-get install -f
timerapp-exp
```

## Артефакты

Полный набор `timerapp-exp-0.11.5-*` (Linux matrix + apk + exe + macos).

## Документация

- [Release notes v0.11.5](https://github.com/alexandrgert/timerapp_exp/blob/main/docs/release-notes-v0.11.5.md)
- [ИНСТРУКЦИЯ.md](https://github.com/alexandrgert/timerapp_exp/blob/main/ИНСТРУКЦИЯ.md)
