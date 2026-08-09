# -*- mode: python ; coding: utf-8 -*-
import os
import webview
from PyInstaller.utils.hooks import collect_all

_WEBVIEW_LIB = os.path.join(os.path.dirname(os.path.abspath(webview.__file__)), 'lib')

#  Fully bundle pip and its vendored deps (needed to `pip install` extension deps
#  at runtime inside the frozen .exe). Collecting only `pip` as a hidden import
#  leaves pip._vendor incomplete -> "Unable to locate finder for 'pip._vendor.distlib'".
_pip_datas, _pip_binaries, _pip_hidden = collect_all('pip')
_st_datas, _st_binaries, _st_hidden = collect_all('setuptools')
_w_datas, _w_binaries, _w_hidden = collect_all('wheel')

a = Analysis(
    ['run_coreframe.pyw'],
    pathex=[],
    binaries=_pip_binaries + _st_binaries + _w_binaries,
    datas=[
        ('static', 'static'),
        ('extensions\\fortune_cookie', 'extensions\\fortune_cookie'),
        (_WEBVIEW_LIB, 'webview\\lib'),
    ] + _pip_datas + _st_datas + _w_datas,
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
    ] + _pip_hidden + _st_hidden + _w_hidden,
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
