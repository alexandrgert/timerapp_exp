from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import default_ui
from ..models import Task


@dataclass
class AppState:
    tasks: list[Task] = field(default_factory=list)
    ui: dict[str, Any] = field(default_factory=default_ui)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [task.to_dict() for task in self.tasks],
            "ui": self.ui,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppState:
        defaults = default_ui()
        ui = dict(data.get("ui") or {})
        for key, value in defaults.items():
            if key not in ui:
                ui[key] = value if not isinstance(value, dict) else dict(value)
        focus = ui.get("focus_timer")
        default_focus = defaults["focus_timer"]
        if not isinstance(focus, dict):
            ui["focus_timer"] = dict(default_focus)
        else:
            for key, value in default_focus.items():
                focus.setdefault(key, value)
        return cls(
            tasks=[Task.from_dict(item) for item in data.get("tasks", [])],
            ui=ui,
        )
