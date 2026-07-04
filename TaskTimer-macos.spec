# -*- mode: python ; coding: utf-8 -*-
# Сборка .app для macOS (onedir + BUNDLE).

import os
import pathlib
import runpy

_spec_dir = pathlib.Path(SPECPATH)
_hidden = runpy.run_path(str(_spec_dir / "packaging" / "pyinstaller_hiddenimports.py"))
HIDDEN_IMPORTS = _hidden["HIDDEN_IMPORTS"]
APP_VERSION = os.environ.get("APP_VERSION", "0.0.0")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TaskTimer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TaskTimer",
)

app = BUNDLE(
    coll,
    name="TaskTimer Experiment.app",
    bundle_identifier="com.timerapp.exp",
    info_plist={
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleDisplayName": "TaskTimer Experiment",
        "NSHighResolutionCapable": True,
    },
)
