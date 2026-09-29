"""Reject an onedir containing ELF imports newer than Ubuntu 20.04's glibc.

Checks version *needs*, not exported version definitions or arbitrary strings.
Run with the Python used for packaging; readelf is provided by binutils.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess


def required_glibc_versions(output: str) -> set[str]:
    in_needs = False
    versions: set[str] = set()
    for line in output.splitlines():
        if line.startswith("Version "):
            in_needs = line.startswith("Version needs section")
        if in_needs:
            versions.update(re.findall(r"Name: GLIBC_(\S+)", line))
    return versions


def incompatible_versions(versions: set[str], maximum: tuple[int, ...]) -> list[str]:
    return sorted(v for v in versions if not re.fullmatch(r"\d+(?:\.\d+)+", v)
                  or tuple(map(int, v.split("."))) > maximum)


def check_tree(root: Path, maximum: tuple[int, ...] = (2, 31)) -> int:
    if not root.is_dir():
        raise ValueError(f"Missing onedir: {root}")
    count = 0
    failures = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        count += 1
        result = subprocess.run(
            ["readelf", "--version-info", "--wide", str(path)],
            text=True, capture_output=True, check=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        bad = incompatible_versions(required_glibc_versions(result.stdout), maximum)
        if bad:
            failures.append(f"{path.relative_to(root)}: {', '.join('GLIBC_' + v for v in bad)}")
    if not count:
        raise ValueError(f"No ELF binaries found in {root}")
    if failures:
        raise ValueError("Incompatible with Ubuntu 20.04:\n" + "\n".join(failures))
    print(f"GLIBC <= {'.'.join(map(str, maximum))}: checked {count} ELF files")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("onedir", type=Path)
    args = parser.parse_args()
    try:
        check_tree(args.onedir)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")
