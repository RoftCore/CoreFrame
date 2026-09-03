# -*- mode: python ; coding: utf-8 -*-
"""Minimal spec for coreframe_helper.exe - elevated operations runner."""

a = Analysis(
    ['coreframe_helper.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['winreg'],
    hookspath=[],
    hooksconfig={},
    excludes=[
        'numpy', 'webview', 'tkinter', 'PIL', 'psutil', 'requests',
        'engineio', 'eventlet', 'clr', 'yt_dlp', 'spotipy',
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='coreframe_helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
