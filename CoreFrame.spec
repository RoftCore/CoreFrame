# -*- mode: python ; coding: utf-8 -*-
import os
import sys as _sys
import webview
from PyInstaller.utils.hooks import collect_all

_WEBVIEW_LIB = os.path.join(os.path.dirname(os.path.abspath(webview.__file__)), 'lib')

#  Fully bundle pip and its vendored deps (needed to `pip install` extension deps
#  at runtime inside the frozen .exe). Collecting only `pip` as a hidden import
#  leaves pip._vendor incomplete -> "Unable to locate finder for 'pip._vendor.distlib'".
_pip_datas, _pip_binaries, _pip_hidden = collect_all('pip')
_st_datas, _st_binaries, _st_hidden = collect_all('setuptools')
_w_datas, _w_binaries, _w_hidden = collect_all('wheel')

#  Bundle the ENTIRE Python standard library (pure .py modules + C extensions).
#  Extension widgets load their third-party deps at runtime from the shared lib
#  (yt_dlp, spotify_scraper, ... any future widget). Those libs also import stdlib
#  modules that a trimmed PyInstaller build never bundles (fileinput, getpass,
#  collections.abc, encodings.*, ..., _sqlite3.pyd), so "import yt_dlp" raised
#  ModuleNotFoundError inside the frozen .exe. Including the full stdlib makes the
#  exe self-sufficient on ANY machine (no system Python required) and future-proof
#  for any widget, without ever bundling third-party libs into the exe.
def _collect_full_stdlib():
    out = set(_sys.stdlib_module_names)
    lib_root = os.path.dirname(os.path.abspath(_sys.modules[os.__name__].__file__))
    for root, dirs, files in os.walk(lib_root):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'test', 'site-packages')]
        rel = os.path.relpath(root, lib_root)
        pkg = '' if rel == '.' else rel.replace(os.sep, '.')
        for f in files:
            if not f.endswith('.py'):
                continue
            if pkg:
                out.add(pkg + ('.' if f != '__init__.py' else '') + (f[:-3] if f != '__init__.py' else ''))
            elif f != '__init__.py':
                out.add(f[:-3])
    out.discard('')
    return sorted(out)

_stdlib_all = _collect_full_stdlib()

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
        # Full stdlib so runtime-loaded widget deps always import cleanly,
        # with no system Python dependency. See _collect_full_stdlib() above.
        *_stdlib_all,
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
