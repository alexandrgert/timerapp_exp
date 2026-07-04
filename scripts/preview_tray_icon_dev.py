#!/usr/bin/env python3
"""Dev-only: PNG-превью иконки трея в dist/ (каталог dist/ в .gitignore)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from timerapp_ag.ui.tray_icon import build_tray_app_icon  # noqa: E402


def main() -> None:
    app = QApplication(sys.argv)
    icon = build_tray_app_icon(app.style())
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)

    for size in (128, 64, 32, 22):
        path = out_dir / f"preview-tray-icon-dev-{size}.png"
        icon.pixmap(size, size).save(str(path))
        print(path)


if __name__ == "__main__":
    main()
