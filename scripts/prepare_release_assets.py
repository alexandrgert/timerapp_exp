"""Validate the complete release matrix and checksum every published package."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tomllib


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    directory = Path(sys.argv[1])
    suffixes = (
        "amd64.deb", "amd64.rpm", "linux-amd64.tar.xz", "linux-amd64.tgz",
        "x86_64.AppImage", "x86_64.flatpak", "amd64.snap", "gentoo-overlay.tar.xz",
        "x86_64.pisi", "amd64.pet", "amd64.pup", "amd64.lzm", "win64.exe",
        "macos-arm64.zip", "android.apk",
    )
    expected = {f"timerapp-exp-{version}-{suffix}" for suffix in suffixes}
    expected.add(f"timerapp-exp-{version}.ebuild")
    actual = {p.name for p in directory.iterdir()}
    if actual != expected:
        raise SystemExit(f"Release asset mismatch: missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}")
    checksums = []
    for name in sorted(expected):
        path = directory / name
        if not path.is_file() or not path.stat().st_size:
            raise SystemExit(f"Empty or invalid release asset: {name}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        checksums.append(f"{digest}  {name}\n")
    (directory / "SHA256SUMS").write_text("".join(checksums))
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    (directory / "build-info.txt").write_text(
        f"Version: {version}\nCommit: {os.environ['GITHUB_SHA']}\n"
        f"Build: https://github.com/{repository}/actions/runs/{run_id}\n"
        f"Packages: {len(expected)}\n"
    )
    print(f"Verified complete release matrix: {len(expected)} packages at {version}")


if __name__ == "__main__":
    main()
