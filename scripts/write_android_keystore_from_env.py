#!/usr/bin/env python3
"""Write android/keystore.properties from ANDROID_* env vars (CI)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REQUIRED_ENV = (
    "ANDROID_KEYSTORE_PASSWORD",
    "ANDROID_KEY_ALIAS",
    "ANDROID_KEY_PASSWORD",
)


def write_keystore_properties(dest: Path, env: dict[str, str]) -> None:
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if missing:
        raise ValueError("Missing env: " + ", ".join(missing))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "storeFile=keystore/tasktimer-release.jks\n"
        f"storePassword={env['ANDROID_KEYSTORE_PASSWORD']}\n"
        f"keyAlias={env['ANDROID_KEY_ALIAS']}\n"
        f"keyPassword={env['ANDROID_KEY_PASSWORD']}\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        root = Path(__file__).resolve().parents[1]
        write_keystore_properties(root / "android" / "keystore.properties", dict(os.environ))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
