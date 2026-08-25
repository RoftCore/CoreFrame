import os
import sys
import json
import threading
import time
import urllib.request
import ctypes

kernel32 = ctypes.windll.kernel32
kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00000080)  # HIGH_PRIORITY_CLASS

_SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, 'CoreFrame-InstanceLock-8420')
if _SINGLE_INSTANCE_MUTEX and kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    # Another instance is running - try to focus its window via API
    kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
    # Wait a bit for the server to be ready
    time.sleep(0.5)
    try:
        req = urllib.request.Request('http://127.0.0.1:8420/api/window/focus', method='POST')
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # If API fails, just exit silently - first instance will handle
    sys.exit(0)

# Check for autostart/minimized flags BEFORE importing heavy modules
AUTOSTART_FLAG = '--autostart' in sys.argv or '--minimized' in sys.argv
MINIMIZED_FLAG = '--minimized' in sys.argv

from app import start_server  # must be before webview — app.py patches subprocess to hide consoles
# Use Edge WebView2 (Chromium) — MSHTML/IE can't render the modern JS frontend
# WebView2 is built-in on Windows 11 and most Windows 10 installations
import webview.util
import webview

# Patch interop_dll_path — AV may delete MEIPASS files after extraction
if hasattr(sys, '_MEIPASS'):
    _orig_interop = webview.util.interop_dll_path
    def _patched_interop(dll_name):
        if dll_name in ('win-arm64', 'win-x64', 'win-x86'):
            meipass_path = os.path.join(sys._MEIPASS, 'webview', 'lib', 'runtimes', dll_name, 'native')
            if os.path.isdir(meipass_path):
                return meipass_path
        return _orig_interop(dll_name)
    webview.util.interop_dll_path = _patched_interop

    # Log STA thread exceptions by patching BrowserForm.__init__
    import webview.platforms.winforms as _wf
    _orig_bform_init = _wf.BrowserView.BrowserForm.__init__
    def _patched_bform_init(self, window, cache_dir):
        try:
            _orig_bform_init(self, window, cache_dir)
        except Exception:
            import traceback
            with open('sta_crash.log', 'w') as f:
                traceback.print_exc(file=f)
            raise
    _wf.BrowserView.BrowserForm.__init__ = _patched_bform_init
    print('[BOOT] Patches applied', flush=True)

HOST = '127.0.0.1'
PORT = 8420
DATA_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'CoreFrame')
CONFIG_PATH = os.path.join(DATA_DIR, 'coreframe.json')

# Static files directory (for loading.html)
if getattr(sys, 'frozen', False):
    STATIC_DIR = os.path.join(sys._MEIPASS, 'static')
else:
    STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

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

def _wait_for_server(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f'http://{HOST}:{PORT}/api/health', timeout=1)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
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

# Create window IMMEDIATELY with local loading page (instant startup)
# CoreFrame dark theme background color to prevent white flash
COREFRAME_BG = '#0d0d1a'
with open(os.path.join(STATIC_DIR, 'loading.html'), 'r', encoding='utf-8') as f:
    loading_html = f.read()
# Use data URL for instant loading - no file I/O, no white background flash
loading_url = 'data:text/html;charset=utf-8,' + urllib.parse.quote(loading_html)

config = load_config()
mode = config.get('window_mode', 'windowed')

# Determine initial window state
initial_fullscreen = False
initial_frameless = False
initial_hidden = AUTOSTART_FLAG  # Start hidden if autostart

if mode == 'fullscreen':
    initial_fullscreen = True
elif mode == 'frameless':
    initial_frameless = True

# Create window IMMEDIATELY with local loading page
window = webview.create_window(
    'CoreFrame',
    loading_url,
    width=1280, height=800,
    fullscreen=initial_fullscreen, 
    frameless=initial_frameless,
    hidden=initial_hidden,  # Start hidden for autostart
    background_color=COREFRAME_BG,
)

# Wait for server in background, then navigate
def _wait_and_navigate():
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
        # Close the loading window
        try:
            window.destroy()
        except Exception:
            pass
        sys.exit(1)
    
    print('[BOOT] Flask ready, navigating to app...', flush=True)
    # Navigate to the real app
    target_url = f'http://{HOST}:{PORT}/?mode={mode}'
    try:
        window.load_url(target_url)
    except Exception:
        pass

threading.Thread(target=_wait_and_navigate, daemon=True, name='server-wait').start()

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
            i.WindowState = getattr(WinForms.FormWindowState, 'Normal')
            i.TopMost = False
    except Exception:
        pass

def minimize_window():
    window.minimize()
    return True

def focus_window():
    """Bring window to front and restore if minimized."""
    try:
        i, WinForms = _get_winform()
        if i:
            i.Invoke(WinForms.MethodInvoker(lambda: _ui_focus(i, WinForms)))
            return True
        else:
            # Fallback for non-winforms
            window.restore()
            window.maximize()
            window.restore()  # Restore to normal size
            return True
    except Exception as e:
        print(f'focus_window error: {e}')
        return False

def _ui_focus(i, WinForms):
    """Runs on UI thread via Invoke - restore and bring to front."""
    try:
        if i.WindowState == getattr(WinForms.FormWindowState, 'Minimized'):
            i.WindowState = getattr(WinForms.FormWindowState, 'Normal')
        i.BringToFront()
        i.TopMost = True
        i.TopMost = False
        i.Focus()
    except Exception:
        pass

window.expose(set_window_mode, minimize_window, focus_window)

# Wire graceful shutdown: close window → webview.start() returns → script exits cleanly
import app as _app_mod
def _shutdown():
    try:
        window.destroy()
    except Exception:
        os._exit(0)
_app_mod._shutdown_callback = _shutdown

print('[BOOT] Calling webview.start...', flush=True)
try:
    webview.start(gui='edgechromium', private_mode=False)
except Exception:
    print('[BOOT] webview.start raised exception!', flush=True)
    import traceback
    with open('crash.log', 'w') as f:
        traceback.print_exc(file=f)
    raise
