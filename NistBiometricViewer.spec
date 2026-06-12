# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path(SPECPATH)

a = Analysis(
    ["installer/pyinstaller_entry.py"],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(project_root / "resources"), "resources"),
        (str(project_root / "installer" / "default_user_files"), "default_user_files"),
    ],
    hiddenimports=["wsq"],
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
    name="NistBiometricViewer",
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
    icon=["resources/nist_biometric_viewer.ico"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NistBiometricViewer",
)
