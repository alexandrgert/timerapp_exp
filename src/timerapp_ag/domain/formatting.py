from __future__ import annotations

from datetime import date


def format_duration(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_hm(total_seconds: int) -> str:
    """Format a duration as HH:MM (seconds dropped)."""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


def format_day_label(day_iso: str) -> str:
    parsed = date.fromisoformat(day_iso)
    return parsed.strftime("%d.%m.%Y")
