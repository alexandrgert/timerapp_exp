#!/bin/sh
# Runs outside Python/Qt, so even bootloader and dynamic linker failures are
# recorded. Each invocation gets a private file (including second instances).
umask 077
app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/timerapp-exp"
log_file=''
if mkdir -p "$log_dir"; then
    # Keep seven days of previous launch logs; never touch application data.
    find "$log_dir" -maxdepth 1 -type f -name 'launch.*.log' -mtime +7 -delete
    log_file=$(mktemp "$log_dir/launch.XXXXXXXX.log") || log_file=''
fi

if [ -n "$log_file" ]; then
    "$app_dir/TaskTimer" "$@" 2>"$log_file"
    status=$?
else
    "$app_dir/TaskTimer" "$@"
    status=$?
fi

if [ "$status" -ne 0 ]; then
    message="TaskTimer завершился с ошибкой (код $status)."
    if [ -n "$log_file" ]; then
        message="$message
Журнал: $log_file"
    else
        message="$message
Не удалось сохранить журнал. Проверьте свободное место и права на $log_dir."
    fi
    printf '%s\n' "$message" >&2
    # Never hang an unattended acceptance test waiting for a dialog.
    if [ "${1:-}" != '--startup-smoke-test' ]; then
        zenity_command=$(command -v zenity)
        notify_command=$(command -v notify-send)
        if [ -n "$zenity_command" ]; then
            "$zenity_command" --error --no-markup --title='TaskTimer — ошибка запуска' --text="$message" || true
        elif [ -n "$notify_command" ]; then
            "$notify_command" --urgency=critical 'TaskTimer — ошибка запуска' "$message" || true
        fi
    fi
elif [ -n "$log_file" ] && [ ! -s "$log_file" ]; then
    rm -f "$log_file"
fi
exit "$status"
