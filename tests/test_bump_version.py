from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "bump_version.py"
_spec = importlib.util.spec_from_file_location("bump_version", _SCRIPTS)
assert _spec and _spec.loader
_bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bump)


@pytest.mark.parametrize(
    ("current", "kind", "expected"),
    [
        ("0.1.0", "patch", "0.1.1"),
        ("0.1.0", "minor", "0.2.0"),
        ("0.1.9", "patch", "0.1.10"),
        ("1.2.3", "major", "2.0.0"),
    ],
)
def test_bump_version(current: str, kind: str, expected: str) -> None:
    assert _bump.bump_version(current, kind) == expected


def test_write_version_updates_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "timerapp-ag"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    old = _bump.write_version("0.2.0", pyproject)
    assert old == "0.1.0"
    assert _bump.read_version(pyproject) == "0.2.0"
