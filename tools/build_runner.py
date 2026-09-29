"""Build the lightweight ext_runner and pack it as runner.zip.

Extension children normally launch the main exe, which costs one MEIPASS
extraction per child (~800MB of temp writes per boot with many extensions).
This builds a minimal onedir runner instead, zips it FLAT (ext_runner.exe at the
zip root, as run_coreframe._ensure_persistent_runner expects) and the main spec
embeds it. Missing runner.zip is not fatal: the app falls back to the main exe.

Usage: python tools/build_runner.py
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist-runner')
BUILT = os.path.join(DIST, 'ext_runner')
ZIP_PATH = os.path.join(ROOT, 'runner.zip')


def main():
    py = sys.executable
    print('[runner] building runner.spec ->', DIST)
    subprocess.check_call([py, '-m', 'PyInstaller', '--noconfirm',
                           '--distpath', DIST, 'runner.spec'], cwd=ROOT)
    if not os.path.isdir(BUILT):
        raise SystemExit('build produced no %s' % BUILT)
    exe = 'ext_runner.exe' if os.name == 'nt' else 'ext_runner'
    if not os.path.isfile(os.path.join(BUILT, exe)):
        raise SystemExit('missing %s in build output' % exe)
    if os.path.isfile(ZIP_PATH):
        os.remove(ZIP_PATH)
    n = 0
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(BUILT):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, BUILT).replace(os.sep, '/'))
                n += 1
    size = os.path.getsize(ZIP_PATH)
    print('[runner] runner.zip: %d files, %.1f MB' % (n, size / 1048576.0))
    if n == 0:
        raise SystemExit('runner.zip is empty')
    shutil.rmtree(DIST, ignore_errors=True)


if __name__ == '__main__':
    main()
