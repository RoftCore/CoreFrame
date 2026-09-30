# -*- mode: python ; coding: utf-8 -*-
import os
import sys as _sys
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(SPECPATH)
# Display name of the child binary. There is one per extension and they have no
# window, so Task Manager shows them as their own groups unless both this name
# AND the version FileDescription match the host exe's (see
# runner_version_info.txt). Matching makes them collapse into the app group.
HOST_NAME = 'CoreFrame'

# Tiny persistent extension runner (stdlib only).
# Built ONEDIR, zipped to runner.zip, embedded in the main one-file exe and
# extracted ONCE to Documents\CoreFrame\bin\runner\. Extension children then
# launch from disk with ZERO per-boot MEIPASS extraction (the old path reused
# the 48MB main exe per child: ~800MB of temp writes every boot).
# Build: py -m PyInstaller --noconfirm --distpath dist-runner runner.spec
# Then: zip dist-runner/ext_runner -> runner.zip (project root) and build main.

# Full stdlib (same rationale as the main exe): marketplace extensions may
# import ANY stdlib module, and there is no system Python to fall back on.
# Third-party (psutil/requests/orjson/PIL) mirrors the main exe bundle —
# extensions relied on those being importable from the old exe-children.
def _collect_full_stdlib():
    out = set(_sys.stdlib_module_names)
    lib_root = os.path.dirname(os.path.abspath(_sys.modules[os.__name__].__file__))
    # Skip GUI/dev-only subpackages: never needed by headless extensions.
    # (idlelib/lib2to3/turtledemo/ensurepip/venv drag tkinter + tcl/tk DLLs.)
    _SKIP = ('__pycache__', 'test', 'site-packages', 'idlelib', 'lib2to3',
             'turtledemo', 'ensurepip', 'venv', 'pydoc_data')
    for root, dirs, files in os.walk(lib_root):
        dirs[:] = [d for d in dirs if d not in _SKIP]
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

_ps_datas, _ps_binaries, _ps_hidden = collect_all('psutil')
_pil_datas, _pil_binaries, _pil_hidden = collect_all('PIL')

a = Analysis(
    ['coreframe/extensions/ext_runner.py'],
    pathex=[],
    binaries=_ps_binaries + _pil_binaries,
    datas=_ps_datas + _pil_datas,
    hiddenimports=[
        'ssl',
        '_ssl',
        'psutil',
        'requests',
        'orjson',
        'PIL.Image',
        'PIL._imaging',
        'PIL._imagingcms',
        'PIL._imagingft',
        'winreg',
        *_stdlib_all,
    ] + _ps_hidden + _pil_hidden,
    hookspath=[],
    hooksconfig={},
    excludes=[
        'numpy',
        'tkinter',
        '_tkinter',
        'tcl',
        'tk',
        'turtle',
        'turtledemo',
        'idlelib',
        'lib2to3',
        'ensurepip',
        'venv',
        'orjson',  # ext_runner falls back to stdlib json (proven)
        # Optional urllib3 TLS backend (guarded try/except there) — stdlib
        # ssl is used instead. Saves the whole cryptography stack.
        'cryptography',
        'bcrypt',
        '_testcapi',
        '_testlimitedcapi',
        '_testinternalcapi',
        'pip',
        'setuptools',
        'wheel',
        'PyInstaller',
        'pytest',
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    # Name/icon/version: this binary is visible in Task Manager (one per
    # extension), so it must read as part of CoreFrame, not as a stray python.
    name=HOST_NAME,
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
    icon=os.path.join(ROOT, 'CoreFrame.ico'),
    version=os.path.join(ROOT, 'runner_version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ext_runner',
)
