# Публикация защиты выбора папки — 20 ноября 2026

Исходники `2d9f24ea6c14b69cdbe6cfb34aba2a4eac1cd169` отправлены в `pwa/development`. Публикация `52c2a11cd7aa5ae085d23ad8efdeef3756c7267d` в `pwa/publish`.

[GitHub Actions 44742485547](https://github.com/alexandrgert/timerapp_exp/actions/runs/44742485547): SUCCESS, attempt 1. 187 тестов PASS, 0 failed/cancelled/skipped. Отдельная проверка реального Service Worker: offline reload, ожидающее/принятое обновление, сохранение таймера и второй вкладки — PASS.

Отчёты `14632006231`, SHA256 скачанного ZIP совпал с GitHub digest `ab8c8a4c50837dd8940d7d45a82e2f494bde57868d157a27f3dc8e625160deeb`.

Публичная HTTPS-проверка: точная revision; при имитации ожидающего системного выбора папки настоящая загрузка JSON откладывается, после отмены появляется сообщение и загрузка возобновляется; HTML-инструкция совпадает с исходником по SHA256, offline reload и настройки сохранены, 320px без горизонтального переполнения. Само native окно Linux на устройстве пользователя не проверено; браузерный тест использует mock picker. Не объявлять системную проблему Chrome устранённой этим выпуском.

README и копия инструкции в main: `2bcdb47f573ec319954cb07d33e7a771633aeb41`, documentation-only `[skip ci]`. Отдельный self-host блок сохранён; Android/desktop/self-host не менялись. Выполнен один разрешённый запуск, повторов не было.
