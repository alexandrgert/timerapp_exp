#!/usr/bin/env python3
"""Semver bump for projects/timerapp_ag/pyproject.toml."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_DIR / "pyproject.toml"
_VERSION_LINE = re.compile(r'^(version\s*=\s*")(\d+\.\d+\.\d+)(")\s*$', re.MULTILINE)


def parse_version(raw: str) -> tuple[int, int, int]:
    parts = raw.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Expected semver MAJOR.MINOR.PATCH, got {raw!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(current: str, kind: str) -> str:
    major, minor, patch = parse_version(current)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown bump kind: {kind!r}")


def read_version(path: Path = PYPROJECT) -> str:
    text = path.read_text(encoding="utf-8")
    match = _VERSION_LINE.search(text)
    if not match:
        raise SystemExit(f"version = \"x.y.z\" not found in {path}")
    return match.group(2)


def write_version(new_version: str, path: Path = PYPROJECT) -> str:
    text = path.read_text(encoding="utf-8")
    match = _VERSION_LINE.search(text)
    if not match:
        raise SystemExit(f"version = \"x.y.z\" not found in {path}")
    old_version = match.group(2)
    updated = _VERSION_LINE.sub(lambda m: f'{m.group(1)}{new_version}{m.group(3)}', text, count=1)
    path.write_text(updated, encoding="utf-8")
    return old_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump semver in pyproject.toml")
    parser.add_argument(
        "kind",
        choices=("patch", "minor", "major"),
        nargs="?",
        default="patch",
        help="patch — мелкие правки; minor — новые фичи; major — ломающие изменения",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Only print the new version, do not write pyproject.toml",
    )
    args = parser.parse_args(argv)

    current = read_version()
    new_version = bump_version(current, args.kind)
    if args.print_only:
        print(new_version)
        return 0

    old_version = write_version(new_version)
    print(f"{old_version} -> {new_version} ({args.kind})", file=sys.stderr)
    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
