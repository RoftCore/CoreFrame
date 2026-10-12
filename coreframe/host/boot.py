"""Early-boot helpers for the launcher: config, splash, server wait, runner extract.

These run before the window exists and must not import webview or Flask.
Bodies are moved verbatim from run_coreframe.pyw; paths arrive as arguments.
"""
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile

_splash_closed = False


def trace(log, msg):
    log.info('[boot] %s', msg)


def read_mode_early(config_path):
    try:
        with open(config_path, encoding='utf-8') as f:
            return json.load(f).get('window_mode', 'windowed')
    except Exception:
        return 'windowed'


def load_config(config_path, saved_mode):
    try:
        with open(config_path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'window_mode': saved_mode}


def save_config(config_path, data_dir, cfg):
    os.makedirs(data_dir, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)


def splash_text(msg):
    """Push a status line to the boot splash. Silent no-op in dev mode."""
    try:
        import pyi_splash
        pyi_splash.update_text(msg)
    except Exception:
        pass


def close_boot_splash():
    """Close the boot splash exactly once. Safe to call from anywhere."""
    global _splash_closed
    if _splash_closed:
        return
    _splash_closed = True
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass


def destroy_splash():
    # Legacy name kept for existing call sites (reveal, watchdog, errors).
    close_boot_splash()


def wait_for_server(host, port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f'http://{host}:{port}/api/health', timeout=1)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.08)
    return False


def show_error(title, msg):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
    except Exception:
        pass


def ensure_persistent_runner(data_dir):
    """Extract the lightweight ext_runner once (stamp-guarded).

    Skipped for --ext-runner children and dev mode. Old children keep
    running from the previous dir until the next boot; extraction only
    ever happens here, before any child spawns.
    """
    try:
        if '--ext-runner' in sys.argv or not getattr(sys, 'frozen', False):
            return
        meipass = getattr(sys, '_MEIPASS', None)
        if not meipass:
            return
        zpath = os.path.join(meipass, 'runner.zip')
        if not os.path.isfile(zpath):
            return
        dest = os.path.join(data_dir, 'bin', 'runner')
        stamp = os.path.join(dest, 'runner.stamp')
        sig = '%d-%d' % (os.path.getsize(zpath), int(os.path.getmtime(zpath)))
        try:
            if os.path.isfile(stamp) and open(stamp, encoding='utf-8').read().strip() == sig \
                    and os.path.isfile(os.path.join(dest, 'CoreFrame.exe')):
                return
        except Exception:
            pass
        tmp = dest + '.new'
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        cur = dest + '.old'
        shutil.rmtree(cur, ignore_errors=True)
        if os.path.isdir(dest):
            os.rename(dest, cur)
        os.rename(tmp, dest)
        shutil.rmtree(cur, ignore_errors=True)
        with open(stamp, 'w', encoding='utf-8') as f:
            f.write(sig)
    except Exception:
        pass