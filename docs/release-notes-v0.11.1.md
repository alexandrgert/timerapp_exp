# TaskTimer Experiment — версия 0.11.1

**Фикс: проверка обновлений только по Releases этой сборки**

Экспериментальный форк: [alexandrgert/timerapp_exp](https://github.com/alexandrgert/timerapp_exp).  
База сравнения: **[v0.11.0](https://github.com/alexandrgert/timerapp_exp/releases/tag/v0.11.0)**.

## Что нового

- Убрана смена репозитория в настройках проверки обновлений (desktop и Android).
- Проверка всегда смотрит **`alexandrgert/timerapp_exp`** — репозиторий этой сборки (избегает ложных сравнений с другой схемой версий, например `timer-app`).
- Старое значение `update_github_repo` в prefs / импорте настроек игнорируется.

Полная матрица Linux и описание проверки обновлений — в [v0.11.0](release-notes-v0.11.0.md).

## Сборки

Та же матрица, что в 0.11.0, с префиксом `timerapp-exp-0.11.1-*` (deb/rpm/tar/AppImage/Flatpak/Snap + experimental + apk/exe/macos).

```bash
wget https://github.com/alexandrgert/timerapp_exp/releases/download/v0.11.1/timerapp-exp-0.11.1-amd64.deb
sudo dpkg -i timerapp-exp-0.11.1-amd64.deb
sudo apt-get install -f
timerapp-exp
```

Предыдущий релиз: [v0.11.0](release-notes-v0.11.0.md).
