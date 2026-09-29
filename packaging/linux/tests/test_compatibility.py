from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PACKAGING = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_glibc", PACKAGING / "check_glibc.py")
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


class AbiTests(unittest.TestCase):
    def test_only_imported_versions_count(self):
        text = """Version definition section '.gnu.version_d' contains 1 entry:
  Name: GLIBC_2.39
Version needs section '.gnu.version_r' contains 1 entry:
  Name: GLIBC_2.2.5  Flags: none  Version: 2
  Name: GLIBC_2.31  Flags: none  Version: 3
"""
        self.assertEqual(abi.required_glibc_versions(text), {"2.2.5", "2.31"})
        self.assertEqual(abi.incompatible_versions({"2.9", "2.31", "2.2.5"}, (2, 31)), [])

    def test_rejects_newer_and_non_numeric_requirements(self):
        self.assertEqual(abi.incompatible_versions({"2.34", "2.38", "ABI_DT_RELR"}, (2, 31)),
                         ["2.34", "2.38", "ABI_DT_RELR"])

    def test_inspects_nested_python_not_just_bootloader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TaskTimer").write_bytes(b"\x7fELF")
            (root / "_internal").mkdir()
            (root / "_internal/libpython.so").write_bytes(b"\x7fELF")
            (root / "VERSION").write_text("0.11.5")

            def readelf(command, **kwargs):
                version = "2.38" if "libpython" in command[-1] else "2.14"
                return subprocess.CompletedProcess(command, 0,
                    f"Version needs section '.gnu.version_r' contains 1 entry:\n  Name: GLIBC_{version}\n")

            with patch.object(abi.subprocess, "run", side_effect=readelf) as call:
                with self.assertRaisesRegex(ValueError, r"_internal/libpython.so: GLIBC_2.38"):
                    abi.check_tree(root)
                self.assertEqual(call.call_count, 2)

    def test_empty_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "No ELF"):
                abi.check_tree(Path(directory))


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tasktimer launcher ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launcher = self.root / "tasktimer-launcher"
        shutil.copyfile(PACKAGING / "tasktimer-launcher.sh", self.launcher)
        self.launcher.chmod(0o755)
        self.bin = self.root / "tools"
        self.bin.mkdir()
        self.dialog = self.root / "dialog.txt"
        self.write_executable(self.bin / "zenity", 'printf "%s\\n" "$@" > "$DIALOG_CAPTURE"\n')
        self.env = {**os.environ, "XDG_STATE_HOME": str(self.root / "state"),
                    "DIALOG_CAPTURE": str(self.dialog),
                    "PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}

    def write_executable(self, path, body):
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_launcher(self, *args):
        return subprocess.run([str(self.launcher), *args], env=self.env,
                              text=True, capture_output=True, timeout=5)

    def logs(self):
        return list((self.root / "state/timerapp-exp").glob("launch.*.log"))

    def test_native_loader_error_is_logged_and_shown(self):
        self.write_executable(self.root / "TaskTimer", "echo 'GLIBC_2.38 not found' >&2\nexit 127\n")
        result = self.run_launcher()
        self.assertEqual(result.returncode, 127)
        self.assertIn("GLIBC_2.38 not found", self.logs()[0].read_text())
        self.assertEqual(self.logs()[0].stat().st_mode & 0o777, 0o600)
        self.assertIn(str(self.logs()[0]), self.dialog.read_text())
        self.assertIn("127", self.dialog.read_text())

    def test_success_passes_arguments_and_has_no_error_dialog(self):
        self.write_executable(self.root / "TaskTimer", 'printf "%s\\n" "$@"\n')
        result = self.run_launcher("argument with spaces", "--example")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "argument with spaces\n--example\n")
        self.assertFalse(self.dialog.exists())
        self.assertEqual(self.logs(), [])

    def test_missing_executable_is_visible(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode, 127)
        self.assertTrue(self.dialog.exists())
        self.assertTrue(self.logs()[0].read_text())

    def test_smoke_failure_cannot_block_on_dialog(self):
        self.write_executable(self.root / "TaskTimer", "exit 1\n")
        self.assertEqual(self.run_launcher("--startup-smoke-test").returncode, 1)
        self.assertFalse(self.dialog.exists())

    def test_log_failure_still_reports_application_exit(self):
        (self.root / "not-a-directory").write_text("occupied")
        self.env["XDG_STATE_HOME"] = str(self.root / "not-a-directory")
        self.write_executable(self.root / "TaskTimer", "exit 42\n")
        result = self.run_launcher()
        self.assertEqual(result.returncode, 42)
        self.assertIn("Не удалось сохранить журнал", self.dialog.read_text())

    def test_separate_invocations_do_not_overwrite_error_logs(self):
        self.write_executable(self.root / "TaskTimer", "echo failure >&2\nexit 1\n")
        self.run_launcher()
        self.run_launcher()
        self.assertEqual(len(self.logs()), 2)


if __name__ == "__main__":
    unittest.main()
