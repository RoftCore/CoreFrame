import os
import sys
import json
import threading
import time
import urllib.request
from app import start_server  # must be before webview — app.py patches subprocess to hide consoles
import webview

HOST = '127.0.0.1'
PORT = 8420
DATA_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'CoreFrame')
CONFIG_PATH = os.path.join(DATA_DIR, 'coreframe.json')

def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'window_mode': 'windowed'}

def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)

def _wait_for_server(timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f'http://{HOST}:{PORT}/api/health', timeout=2)
            if r.status == 200:
                time.sleep(0.3)
                r = urllib.request.urlopen(f'http://{HOST}:{PORT}/api/health', timeout=2)
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def _show_error(title, msg):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
    except Exception:
        pass

debug_mode = not getattr(sys, 'frozen', False)
t = threading.Thread(target=start_server, kwargs={'host': HOST, 'port': PORT, 'debug': debug_mode}, daemon=True)
t.start()

if not _wait_for_server():
    _show_error("CoreFrame",
        f"CoreFrame failed to start on {HOST}:{PORT}.\n\n"
        "Possible causes:\n"
        "- Another instance is already running\n"
        "- Port {PORT} is in use by another application\n"
        "- An extension failed to load\n\n"
        "Check the log at:\n"
        f"{os.path.join(DATA_DIR, 'coreframe.log')}"
    )
    sys.exit(1)

config = load_config()
mode = config.get('window_mode', 'windowed')

# Always start windowed; the JS applies saved mode after load
window = webview.create_window(
    'CoreFrame',
    f'http://{HOST}:{PORT}/?mode={mode}',
    width=1280, height=800,
    fullscreen=False, frameless=False,
)

_winforms_available = None
def _get_winform():
    global _winforms_available
    if _winforms_available is False:
        return None, None
    try:
        import clr
        import System.Windows.Forms as WinForms
        _winforms_available = True
        gui = window.gui
        uid = window.uid
        if not gui or not uid:
            return None, WinForms
        i = gui.BrowserView.instances.get(uid)
        return i, WinForms
    except Exception:
        _winforms_available = False
        return None, None

def set_window_mode(new_mode):
    cfg = load_config()
    cfg['window_mode'] = new_mode
    save_config(cfg)
    i, WinForms = _get_winform()
    applied = False
    try:
        if i:
            i.Invoke(WinForms.MethodInvoker(lambda: _ui_set_mode(i, WinForms, new_mode)))
            applied = True
        else:
            if new_mode == 'windowed':
                window.restore()
                window.resize(1280, 800)
            else:
                window.maximize()
            applied = True
    except Exception:
        applied = False
    return applied

def _ui_set_mode(i, WinForms, new_mode):
    """Runs on UI thread via Invoke."""
    try:
        screen = WinForms.Screen.FromHandle(i.Handle)
        if new_mode == 'fullscreen':
            i.FormBorderStyle = getattr(WinForms.FormBorderStyle, 'None')
            i.Bounds = screen.Bounds
            i.TopMost = True
        elif new_mode == 'frameless':
            i.FormBorderStyle = getattr(WinForms.FormBorderStyle, 'None')
            i.Bounds = screen.WorkingArea
            i.TopMost = False
        else:
            i.FormBorderStyle = WinForms.FormBorderStyle.Sizable
            i.WindowState = WinForms.WindowState.Normal
            i.TopMost = False
    except Exception:
        pass

def minimize_window():
    window.minimize()
    return True

window.expose(set_window_mode, minimize_window)
webview.start(private_mode=False)
