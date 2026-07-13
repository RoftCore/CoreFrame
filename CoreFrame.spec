# -*- mode: python ; coding: utf-8 -*-
import os, sys, glob

_py_dll_dir = os.path.join(sys.base_prefix, 'DLLs')
_ssl_files = glob.glob(os.path.join(_py_dll_dir, 'libcrypto*')) + \
             glob.glob(os.path.join(_py_dll_dir, 'libssl*'))
_ssl_bins = [(f, '.') for f in _ssl_files]

a = Analysis(
    ['run_coreframe.pyw'],
    pathex=[],
    binaries=_ssl_bins,
    datas=[
        ('static', 'static'),
        ('extensions\\fortune_cookie', 'extensions\\fortune_cookie'),
    ],
    hiddenimports=[
        'ssl',
        '_ssl',
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
    icon='CoreFrame.ico',
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
