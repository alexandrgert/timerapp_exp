"""Константы доменного слоя и значения по умолчанию для ui."""

SCHEMA_VERSION = 2

DEFAULT_REMINDER_INTERVAL_MINUTES = 40
REMINDER_INTERVAL_MIN = 1
REMINDER_INTERVAL_MAX = 24 * 60
REMINDER_GRACE_MINUTES = 5

DEFAULT_FOCUS_SELECTED_MINUTES = 20


def default_ui() -> dict:
    """Новый словарь ui с дефолтами (без общих mutable-ссылок между экземплярами)."""
    return {
        "filter_open_only": False,
        "reminder_interval_minutes": DEFAULT_REMINDER_INTERVAL_MINUTES,
        "focus_timer": {
            "selected_minutes": DEFAULT_FOCUS_SELECTED_MINUTES,
            "duration_minutes": None,
            "ends_at": None,
        },
    }
