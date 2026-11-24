"""One version, three files: bump the release version or check that they agree.

    python tools/bump_version.py            # 1.1.0 -> 1.1.1, what a rebuild needs
    python tools/bump_version.py --set 1.2.0
    python tools/bump_version.py --check    # CI: exit 1 when the files disagree

The patch is a number, not a digit: 1.1.0 -> 1.1.37 is fine, and MAJOR.MINOR
are reserved for official releases.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'coreframe' / 'config.py'
VERSION_FILES = [ROOT / 'version_info.txt', ROOT / 'runner_version_info.txt']

CONFIG_RE = re.compile(r"APP_VERSION\s*=\s*'(\d+\.\d+\.\d+)'")
TUPLE_RE = re.compile(r"(filevers|prodvers)=\((\d+), (\d+), (\d+), (\d+)\)")
STRING_RE = re.compile(r"StringStruct\('(FileVersion|ProductVersion)', '([^']*)'\)")


def read_all():
    """Return {path: version or None} for the three files that carry the version."""
    found = {}
    match = CONFIG_RE.search(CONFIG.read_text(encoding='utf-8'))
    found[CONFIG] = match.group(1) if match else None
    for path in VERSION_FILES:
        text = path.read_text(encoding='utf-8')
        values = {'.'.join(m.groups()[1:4]) for m in TUPLE_RE.finditer(text)}
        values |= {m.group(2) for m in STRING_RE.finditer(text)}
        found[path] = values.pop() if len(values) == 1 else None
    return found


def write_all(version):
    """Rewrite the three files, keeping the fourth tuple field and the file layout."""
    major, minor, patch = (int(part) for part in version.split('.'))
    text = CONFIG.read_text(encoding='utf-8')
    CONFIG.write_text(CONFIG_RE.sub(f"APP_VERSION = '{version}'", text), encoding='utf-8')
    for path in VERSION_FILES:
        text = path.read_text(encoding='utf-8')
        text = TUPLE_RE.sub(
            lambda m: f"{m.group(1)}=({major}, {minor}, {patch}, {m.group(5)})", text)
        text = STRING_RE.sub(
            lambda m: f"StringStruct('{m.group(1)}', '{version}')", text)
        path.write_text(text, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Release version, one source of truth.')
    parser.add_argument('--check', action='store_true', help='exit 1 when the files disagree')
    parser.add_argument('--set', dest='new_version', metavar='X.Y.Z', help='write this version')
    args = parser.parse_args()

    found = read_all()
    shown = {str(path.relative_to(ROOT)): value for path, value in found.items()}

    if args.check:
        if None in found.values() or len(set(found.values())) != 1:
            print('version mismatch:')
            for name, value in shown.items():
                print(f'  {name}: {value}')
            return 1
        print(f'version in sync: {next(iter(found.values()))}')
        return 0

    current = found[CONFIG]
    if not current:
        print('APP_VERSION not found in coreframe/config.py')
        return 1

    if args.new_version:
        new_version = args.new_version
        if not re.fullmatch(r'\d+\.\d+\.\d+', new_version):
            print(f'not a X.Y.Z version: {new_version}')
            return 1
    else:
        major, minor, patch = current.split('.')
        new_version = f'{major}.{minor}.{int(patch) + 1}'

    if new_version == current:
        print(f'already at {current}')
        return 0

    write_all(new_version)
    print(f'{current} -> {new_version}')
    for name in shown:
        print(f'  {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
