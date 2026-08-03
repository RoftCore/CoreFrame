# -*- mode: python ; coding: utf-8 -*-
import os
import webview

_WEBVIEW_LIB = os.path.join(os.path.dirname(os.path.abspath(webview.__file__)), 'lib')

a = Analysis(
    ['run_coreframe.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('extensions\\fortune_cookie', 'extensions\\fortune_cookie'),
        (_WEBVIEW_LIB, 'webview\\lib'),
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
        'webview.platforms.edgechromium',
        'clr',
        'pip',
        'setuptools',
        'wheel',
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
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='CoreFrame',
    icon='CoreFrame.ico',
    version='version_info.txt',
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
