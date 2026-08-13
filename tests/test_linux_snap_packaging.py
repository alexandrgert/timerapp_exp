from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[1]
SNAP_PACKAGER = PROJECT_DIR / "packaging" / "linux" / "package_snap_from_onedir.sh"


@pytest.mark.skipif(
    shutil.which("snap") is None or shutil.which("unsquashfs") is None,
    reason="snap and squashfs-tools are required",
)
def test_snap_packager_works_without_snapcraft(tmp_path: Path) -> None:
    onedir = tmp_path / "TaskTimer"
    onedir.mkdir()
    executable = onedir / "TaskTimer"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    dist_dir = tmp_path / "dist"

    env = os.environ.copy()
    env.update(
        {
            "ONEDIR": str(onedir),
            "DIST_DIR": str(dist_dir),
            "VERSION": "0.10.0",
        }
    )
    subprocess.run([SNAP_PACKAGER], env=env, check=True)

    artifact = dist_dir / "timerapp-exp-0.10.0-amd64.snap"
    assert artifact.stat().st_size > 0
