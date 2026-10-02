# Проверка выпуска TaskTimer Experiment 0.11.8

[Релиз v0.11.8](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.11.8)
опубликован как Latest: 16 пакетов Linux, Windows, macOS arm64 и Android, а также
`SHA256SUMS` и `build-info.txt`.

## Происхождение пакетов

- **Desktop:** [GitHub Actions 36859044412](https://github.com/alexandrgert/timerapp_exp/actions/runs/36859044412),
  коммит `29db6bff343e39526b43d16627aeb3879909b648`. Все desktop-пакеты
  использованы без пересборки. Полный запуск завершился ошибкой Android;
  успешные desktop-задания и четыре проверки Ubuntu проверены отдельно.
- **Android и публикация:** [GitHub Actions 36975767255](https://github.com/alexandrgert/timerapp_exp/actions/runs/36975767255),
  коммит `18f0c5d2a74326da5f82852c527d0a9fe206330a`, успешный recovery-запуск.
  Он проверяет прежний коммит, задания, точные ID и SHA256 desktop-архивов,
  разрешённые изменения исходников и полную матрицу из 16 пакетов.
- `build-info.txt` указывает раздельные коммиты и запуски desktop/Android.
  Общий коммит публикации не означает пересборку desktop из этого коммита.

## Подтверждённые проверки

- Desktop: 458 тестов и 9 fixture subtests, всего 467 успешных записей JUnit.
- Linux builder Ubuntu 20.04: 457 тестов и 9 fixture subtests прошли, 1 пропуск.
- Установка и запуск главного окна DEB: Ubuntu 20.04, 22.04, 24.04 и 26.04.
- Android: компиляция release unit-тестов, 111 тестов без ошибок и пропусков;
  сборка APK, проверка подписи, `com.timerapp.exp`, версия `0.11.8`, код `1108`.
  [Артефакт отчётов Android](https://github.com/alexandrgert/timerapp_exp/actions/runs/36975767255/artifacts/11213706334).
- Перед публикацией проверены наличие всех 16 пакетов и контрольные суммы
  повторно использованных desktop-архивов; созданы суммы конечных пакетов.
- После публикации все 16 записей `SHA256SUMS` сверены с GitHub asset digests.
  Скачанные `SHA256SUMS` и `build-info.txt` также совпали со своими GitHub digests;
  в `build-info.txt` подтверждено корректное раздельное происхождение пакетов.

| Пакет | Размер, байт | SHA256 |
|---|---:|---|
| `timerapp-exp-0.11.8-android.apk` | 146784306 | `bfc4127dfe653cb4344304211143a6d1848d335b63fdb8fe0c2fef7c8f93811e` |
| `timerapp-exp-0.11.8-amd64.deb` | 56532488 | `f6db40378067c1287324d253d0082d58f59919bf2eb6b3d4c2f04ec8c564191a` |

## Что остаётся проверить вручную

Обновление и работа на физических телефонах/компьютерах, WebDAV между устройствами
с пользовательским сервером, микрофон и диктовка, Wayland/трей и установка
остальных форматов не подтверждены этими заданиями. Антивирусное сканирование
новых пакетов не выполнялось. Windows/macOS остаются без подписи издателя/Apple notarization.

Публичный HTTPS-сайт PWA через GitHub Pages ещё не опубликован; этот native-релиз
его не размещает. Ранее прошедшая отдельная PWA-проверка браузера, Service Worker
и контрольной русской записи не заменяет проверку публичного сайта и телефона:
[отчёт PWA](../pwa/docs/verification-2026-10-01.md).
