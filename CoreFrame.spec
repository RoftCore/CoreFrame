# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['E:\\Programming\\CoreFrame\\run_coreframe.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('E:\\Programming\\CoreFrame\\extensions\\fortune_cookie', 'extensions\\fortune_cookie'),
    ],
    hiddenimports=[
        'engineio.async_drivers.threading',
        'eventlet',
        'psutil',
        'requests',
        'PIL.Image',
        'PIL._imaging',
        'PIL._imagingcms',
        'PIL._imagingft',
        'winreg',
        'tkinter',
        'tkinter.filedialog',
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.win32',
    ],
    hookspath=[],
    hooksconfig={},
    excludes=[
        'numpy',
        'pythoncom',
        'dns.win32util',
        'yt_dlp',
        'SpotipyFree',
        'spotapi',
        'pymongo',
        'curl_cffi',
        'pycowsay',
        'GPUtil',
        'wmi',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='CoreFrame',
    icon='E:\\Programming\\CoreFrame\\CoreFrame.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# onefile — no COLLECT step
