"""Compile the single-exe launcher that embeds host.zip and splash.png.

csc from .NET Framework 4.8, no extra toolchain: /target:winexe, resources
embedded so a normal launch unpacks nothing at all. Stamp comes from host.zip
(size-mtime), the same convention ensure_persistent_runner uses for runner.zip.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist')
ZIP = os.path.join(DIST, 'host.zip')
OUT = os.path.join(DIST, 'CoreFrame.exe')
SRC = os.path.join(ROOT, 'launcher', 'CoreFrameStub.cs')
ICON = os.path.join(ROOT, 'CoreFrame.ico')
SPLASH = os.path.join(ROOT, 'splash.png')
VERSION_INFO = os.path.join(ROOT, 'version_info.txt')
GEN = os.path.join(DIST, 'stub_build')

STUB_INFO = """using System.Reflection;

[assembly: AssemblyTitle("CoreFrame")]
[assembly: AssemblyProduct("CoreFrame")]
[assembly: AssemblyFileVersion("%(v4)s")]
[assembly: AssemblyVersion("%(v4)s")]
[assembly: AssemblyInformationalVersion("%(v3)s")]

namespace CoreFrameStub
{
    internal static class StubInfo
    {
        public const string Stamp = "%(stamp)s";
        public const string Version = "%(v3)s";
        public const string Payload = "host.zip";
        public const string Splash = "splash.png";
    }
}
"""


def read_version():
    """(major, minor, patch[, build]) from version_info.txt, the exe's own version resource."""
    try:
        with open(VERSION_INFO, encoding='utf-8') as f:
            text = f.read()
        m = re.search(r'prodvers=\((\d+),\s*(\d+),\s*(\d+)(?:,\s*(\d+))?\)', text)
        if m:
            return tuple(int(g) for g in m.groups() if g is not None)
    except OSError:
        pass
    return (0, 0, 0, 0)


def find_csc():
    windir = os.environ.get('WINDIR', r'C:\Windows')
    for sub in ('Framework64', 'Framework'):
        p = os.path.join(windir, 'Microsoft.NET', sub, 'v4.0.30319', 'csc.exe')
        if os.path.isfile(p):
            return p
    return None


def framework_dir(csc):
    return os.path.dirname(csc)


def main():
    if not os.path.isfile(ZIP):
        print('missing %s - run tools/build_host_zip.py first' % ZIP)
        return 1
    csc = find_csc()
    if not csc:
        print('no csc.exe found (.NET Framework 4.x)')
        return 1

    size = os.path.getsize(ZIP)
    stamp = '%d-%d' % (size, int(os.path.getmtime(ZIP)))
    ver = read_version()
    v3 = '.'.join(str(n) for n in ver[:3])
    v4 = '.'.join(str(n) for n in (list(ver) + [0, 0, 0, 0])[:4])
    os.makedirs(GEN, exist_ok=True)
    info_path = os.path.join(GEN, 'StubInfo.cs')
    with open(info_path, 'w', encoding='utf-8') as f:
        f.write(STUB_INFO % {'stamp': stamp, 'v3': v3, 'v4': v4})

    fw = framework_dir(csc)
    refs = ['System.dll', 'System.Core.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll',
            'System.IO.Compression.dll', 'System.IO.Compression.FileSystem.dll']
    cmd = [csc, '/nologo', '/target:winexe', '/platform:anycpu', '/optimize+',
           '/out:' + OUT, '/win32icon:' + ICON,
           '/resource:%s,host.zip' % ZIP, '/resource:%s,splash.png' % SPLASH]
    for r in refs:
        cmd.append('/r:' + os.path.join(fw, r))
    cmd += [SRC, info_path]

    print('stamp %s' % stamp)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stdout.strip():
        print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr.strip() or 'csc failed')
        return res.returncode

    out_size = os.path.getsize(OUT)
    print('CoreFrame.exe: %.1f MB (payload %.1f MB, version %s, stamp %s)'
          % (out_size / 1048576.0, size / 1048576.0, v3, stamp))
    with open(os.path.join(DIST, 'stub_stamp.json'), 'w', encoding='utf-8') as f:
        json.dump({'stamp': stamp, 'version': v3, 'exe_size': out_size, 'payload_size': size}, f)
    return 0


if __name__ == '__main__':
    sys.exit(main())
