"""Mirror coreframe/extensions/ext_runner.py into run_coreframe.pyw.

The main exe doubles as the extension child: `CoreFrame.exe --ext-runner <cfg>`
re-executes itself, and that check must run before any heavy import. Importing
the module by name is not an option because coreframe/__init__.py pulls
coreframe.app (Flask and friends), which is exactly what --ext-runner avoids.
So the child source is embedded as a verbatim raw string, with
coreframe.extensions.ext_runner as the only editable copy.

    python tools/sync_ext_runner_source.py           rewrite the mirror
    python tools/sync_ext_runner_source.py --check   exit 1 if out of sync
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, 'coreframe', 'extensions', 'ext_runner.py')
HOST = os.path.join(ROOT, 'run_coreframe.pyw')

BEGIN = "_EXT_RUNNER_SOURCE = r'''"
CLOSER = "'''"


def read_text(path):
    with io.open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def write_text(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)


def block_bounds(lines):
    """Return (start, end) line indexes of the mirror body, exclusive."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == BEGIN:
            start = i
            break
    if start is None:
        raise SystemExit('sync: %s marker not found in %s' % (BEGIN, HOST))
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == CLOSER:
            return start + 1, j
    raise SystemExit('sync: closing %r not found in %s' % (CLOSER, HOST))


def render(source_text):
    return source_text.rstrip('\n') + '\n'


def main():
    check = '--check' in sys.argv[1:]
    source_text = read_text(SOURCE)
    if "'''" in source_text:
        raise SystemExit('sync: source contains a triple quote that breaks r-string mirror')
    host_text = read_text(HOST)
    lines = host_text.split('\n')
    lo, hi = block_bounds(lines)
    current = '\n'.join(lines[lo:hi]) + '\n'
    wanted = render(source_text)
    if current == wanted:
        print('sync: ext_runner mirror is in sync (%d lines)' % len(source_text.splitlines()))
        return 0
    if check:
        print('sync: OUT OF SYNC, run tools/sync_ext_runner_source.py')
        return 1
    lines[lo:hi] = wanted.split('\n')[:-1]
    write_text(HOST, '\n'.join(lines))
    print('sync: rewrote %d lines of %s' % (len(wanted.splitlines()), os.path.basename(HOST)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
