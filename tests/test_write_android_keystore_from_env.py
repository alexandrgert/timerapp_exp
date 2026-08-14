from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "write_android_keystore_from_env.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("write_android_keystore_from_env", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_keystore_properties(tmp_path: Path) -> None:
    mod = _load_module()
    dest = tmp_path / "keystore.properties"
    mod.write_keystore_properties(
        dest,
        {
            "ANDROID_KEYSTORE_PASSWORD": "store-secret",
            "ANDROID_KEY_ALIAS": "tasktimer",
            "ANDROID_KEY_PASSWORD": "key-secret",
        },
    )
    text = dest.read_text(encoding="utf-8")
    assert "storeFile=keystore/tasktimer-release.jks" in text
    assert "storePassword=store-secret" in text
    assert "keyAlias=tasktimer" in text
    assert "keyPassword=key-secret" in text


def test_write_keystore_properties_requires_env(tmp_path: Path) -> None:
    mod = _load_module()
    with pytest.raises(ValueError, match="Missing env"):
        mod.write_keystore_properties(tmp_path / "keystore.properties", {})
