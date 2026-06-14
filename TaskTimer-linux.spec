# -*- mode: python ; coding: utf-8 -*-
# Сборка каталога dist/TaskTimer/ для .deb (Linux amd64, onedir — надёжнее для Qt).

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "timerapp_ag.main",
        "timerapp_ag.main_window",
        "timerapp_ag.controller",
        "timerapp_ag.storage",
        "timerapp_ag.models",
        "timerapp_ag.bitrix",
        "timerapp_ag.bitrix_config",
        "timerapp_ag.single_instance",
    ],
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
