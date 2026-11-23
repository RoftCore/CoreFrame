"""Zip the onedir host build into dist/host.zip (contents at the archive root).

Mirrors tools/build_runner.py: the launcher stub embeds this zip and deploys it
once under DATA_DIR\\bin\\host, stamp-guarded exactly like runner.zip.
"""
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'dist', 'host')
OUT = os.path.join(ROOT, 'dist', 'host.zip')
HELPER = os.path.join(ROOT, 'dist', 'coreframe_helper.exe')


def main():
    if not os.path.isdir(SRC):
        print('missing %s - build CoreFrame.spec first' % SRC)
        return 1
    if not os.path.isfile(os.path.join(SRC, 'CoreFrame.exe')):
        print('missing CoreFrame.exe in %s' % SRC)
        return 1
    # bridge._get_helper_path() looks beside the exe: without it every admin op fails (pitfall 66).
    if not os.path.isfile(HELPER):
        print('missing %s - run: py -3.13 -m PyInstaller --noconfirm coreframe_helper.spec' % HELPER)
        return 1
    shutil.copy2(HELPER, os.path.join(SRC, 'coreframe_helper.exe'))

    entries = 0
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, dirs, files in os.walk(SRC):
            dirs.sort()
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, SRC).replace(os.sep, '/')
                z.write(full, rel)
                entries += 1

    size = os.path.getsize(OUT)
    mtime = int(os.path.getmtime(OUT))
    stamp = '%d-%d' % (size, mtime)
    print('host.zip: %d files, %.1f MB, stamp %s' % (entries, size / 1048576.0, stamp))
    with open(os.path.join(ROOT, 'dist', 'host_stamp.json'), 'w', encoding='utf-8') as f:
        json.dump({'stamp': stamp, 'size': size, 'files': entries}, f)
    return 0


if __name__ == '__main__':
    sys.exit(main())
