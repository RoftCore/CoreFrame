import os
import sys
import json
import math
import faulthandler
import threading
import time
import queue as _queue
import urllib.request
import ctypes
from ctypes import wintypes

# Freeze forensics: dump ALL thread stacks to coreframe.log every 15s.
# When the app hangs, the last dump shows exactly where each thread is stuck.
_boot_log_file = None

def _start_stack_dumper():
    global _boot_log_file
    try:
        d = os.path.join(_real_docs_dir(), 'CoreFrame')
        os.makedirs(d, exist_ok=True)
        _boot_log_file = open(os.path.join(d, 'coreframe.log'), 'a', encoding='utf-8')
        _boot_log_file.write('\n===== %s launch =====\n' % time.strftime('%H:%M:%S'))
        _boot_log_file.flush()
        faulthandler.dump_traceback_later(15, repeat=True, file=_boot_log_file)
    except Exception:
        pass

# Serialized UI-worker: EVERY WinForms/pythonnet touch goes through this single
# thread. Concurrent Invoke/enumeration from multiple threads was causing
# intermittent freezes after load.
_uiq = _queue.Queue()

def _ui_worker():
    while True:
        fn = _uiq.get()
        try:
            fn()
        except Exception as e:
            try:
                _trace(f'uiq error: {e}')
            except Exception:
                pass
        finally:
            _uiq.task_done()

threading.Thread(target=_ui_worker, daemon=True, name='uiq').start()

def _post_ui(fn):
    """Fire-and-forget: run fn(serialized) on the UI worker thread."""
    _uiq.put(fn)

kernel32 = ctypes.windll.kernel32
kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00000080)  # HIGH_PRIORITY_CLASS

_SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, 'CoreFrame-InstanceLock-8420')
if _SINGLE_INSTANCE_MUTEX and kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
    time.sleep(0.5)
    try:
        req = urllib.request.Request('http://127.0.0.1:8420/api/window/focus', method='POST')
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass
    sys.exit(0)

def _real_docs_dir():
    """Same API as app.py (SHGetFolderPath) — handles redirected Documents."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buf)
        if buf.value:
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')

DATA_DIR_EARLY = os.path.join(_real_docs_dir(), 'CoreFrame')
os.makedirs(DATA_DIR_EARLY, exist_ok=True)
_start_stack_dumper()

import logging
LOG_PATH_EARLY = os.path.join(DATA_DIR_EARLY, 'coreframe.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_PATH_EARLY, encoding='utf-8')],
)
log = logging.getLogger('CoreFrame')

def _trace(msg):
    log.info('[boot] %s', msg)

_trace('--- launch ---')

# Flags BEFORE importing heavy modules
AUTOSTART_FLAG = '--autostart' in sys.argv or '--minimized' in sys.argv
MINIMIZED_FLAG = '--minimized' in sys.argv

def _read_mode_early():
    try:
        with open(os.path.join(DATA_DIR_EARLY, 'coreframe.json'), encoding='utf-8') as f:
            return json.load(f).get('window_mode', 'windowed')
    except Exception:
        return 'windowed'

SAVED_MODE = _read_mode_early()

# ══════════════════════════════════════════════════════════════════
# NATIVE SPLASH — pixel-matched replica of static/loading.html so the
# user effectively sees THE loading screen from the very first frame.
# Pure Win32/GDI, zero dependencies, created before heavy imports.
# ══════════════════════════════════════════════════════════════════
_splash_hwnd = None
_splash_angle = [0]
_splash_tick = [0]
_splash_w = [800]
_splash_h = [600]

BG_RGB      = (0x0D, 0x0D, 0x1A)   # #0d0d1a  (r,g,b)
GRID_RGB    = (0x14, 0x14, 0x26)   # subtle grid line
CYAN_RGB    = (0x00, 0xD4, 0xFF)   # #00d4ff
MUTED_RGB   = (0x70, 0x60, 0x60)   # #606070

def _rgb(c):
    return wintypes.COLORREF((c[2] << 16) | (c[1] << 8) | c[0])

class _PAINTSTRUCT(ctypes.Structure):
    _fields_ = [('hdc', wintypes.HDC), ('fErase', wintypes.BOOL),
                ('rcPaint', wintypes.RECT), ('fRestore', wintypes.BOOL),
                ('fIncUpdate', wintypes.BOOL), ('rgbReserved', ctypes.c_byte * 32)]

_SplashProc = ctypes.WINFUNCTYPE(ctypes.c_longlong,
                                 wintypes.HWND, ctypes.c_uint,
                                 wintypes.WPARAM, wintypes.LPARAM)

_splash_res = {}   # cached GDI handles (fonts/pens), created once
_paint_err_n = [0]

def _splash_init_gdi():
    """Declare EVERY prototype with proper 64-bit types ONCE, then create
    cached GDI objects. Without argtypes, HDCs truncate to 32-bit -> OverflowError."""
    gdi = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    # ─── gdi32 ───
    gdi.CreateSolidBrush.restype = ctypes.c_void_p
    gdi.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi.CreatePen.restype = ctypes.c_void_p
    gdi.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
    gdi.CreateFontW.restype = ctypes.c_void_p
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 13 + [wintypes.LPCWSTR]  # 14 params total
    gdi.SelectObject.restype = ctypes.c_void_p
    gdi.SelectObject.argtypes = [wintypes.HDC, ctypes.c_void_p]
    gdi.DeleteObject.restype = ctypes.c_int
    gdi.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi.MoveToEx.restype = ctypes.c_int
    gdi.MoveToEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi.LineTo.restype = ctypes.c_int
    gdi.LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.SetBkMode.restype = ctypes.c_int
    gdi.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.SetTextColor.restype = wintypes.COLORREF
    gdi.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi.AngleArc.restype = ctypes.c_int
    gdi.AngleArc.argtypes = [wintypes.HDC, ctypes.c_float, ctypes.c_float,
                             ctypes.c_float, ctypes.c_float, ctypes.c_float]
    gdi.TextOutW.restype = ctypes.c_int
    gdi.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                             wintypes.LPCWSTR, ctypes.c_int]

    # ─── user32 ───
    user32.FillRect.restype = ctypes.c_int
    user32.FillRect.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.HBRUSH]
    user32.DrawTextW.restype = ctypes.c_int
    user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                                 wintypes.LPRECT, ctypes.c_uint]
    user32.GetClientRect.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [wintypes.HWND, wintypes.LPRECT]
    user32.InvalidateRect.restype = ctypes.c_int
    user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
    user32.SetTimer.restype = ctypes.c_size_t
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, ctypes.c_uint, ctypes.c_void_p]
    user32.PostMessageW.restype = ctypes.c_int
    user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.DestroyWindow.restype = ctypes.c_int
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DefWindowProcW.restype = ctypes.c_longlong
    user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetMessageW.restype = ctypes.c_int
    user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
    user32.TranslateMessage.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.c_void_p]
    user32.DispatchMessageW.restype = ctypes.c_longlong
    user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.GetWindowRect.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, wintypes.LPRECT]
    user32.SetWindowPos.restype = ctypes.c_int
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                    ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.RegisterClassExW.restype = ctypes.c_uint16
    user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, ctypes.c_void_p,
                                       wintypes.HINSTANCE, ctypes.c_void_p]

    # ─── kernel32 ───
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

    # ─── cached objects ───
    _splash_res['brush_bg'] = gdi.CreateSolidBrush(_rgb(BG_RGB))
    _splash_res['pen_grid'] = gdi.CreatePen(0, 1, _rgb(GRID_RGB))
    _splash_res['pen_ring'] = gdi.CreatePen(0, 3, _rgb(CYAN_RGB))
    _splash_res['font_logo'] = gdi.CreateFontW(-46, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 0, 0, 'Consolas')
    _splash_res['font_tag'] = gdi.CreateFontW(-13, 0, 0, 0, 500, 0, 0, 0, 0, 0, 0, 0, 0, 'Consolas')
    _splash_res['font_status'] = gdi.CreateFontW(-14, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 0, 0, 'Consolas')

def _splash_draw(hdc, w, h):
    gdi = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    R = _splash_res

    # Background fill (solid, no grid)
    user32.FillRect.restype = ctypes.c_int
    user32.FillRect.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.HBRUSH]
    rc = wintypes.RECT(0, 0, w, h)
    user32.FillRect(hdc, ctypes.byref(rc), wintypes.HBRUSH(R['brush_bg']))

    cx, cy = w // 2, h // 2
    gdi.SetBkMode(hdc, 1)  # TRANSPARENT

    # ── Logo, letter-spaced ──
    title = 'CoreFrame'
    old_f = gdi.SelectObject(hdc, ctypes.c_void_p(R['font_logo']))
    gdi.SetTextColor(hdc, _rgb(CYAN_RGB))
    total = 0
    widths = []
    for ch in title:
        r = wintypes.RECT(0, 0, 0, 0)
        user32.DrawTextW(hdc, ch, -1, ctypes.byref(r), 0x421)  # CALCRECT|SINGLELINE|NOPREFIX
        wid = max(1, r.right - r.left)
        widths.append(wid)
        total += wid + 8
    x = cx - (total - 8) // 2
    y_logo = cy - 135
    for ch, cwid in zip(title, widths):
        gdi.TextOutW(hdc, x, y_logo, ch, len(ch))
        x += cwid + 8
    gdi.SelectObject(hdc, old_f)

    # ── Tagline ──
    old_f2 = gdi.SelectObject(hdc, ctypes.c_void_p(R['font_tag']))
    gdi.SetTextColor(hdc, _rgb((0x60, 0x60, 0x70)))
    user32.DrawTextW(hdc, 'P E R S O N A L   C O N T R O L   C E N T E R', -1,
                     ctypes.byref(wintypes.RECT(cx-420, y_logo+60, cx+420, y_logo+88)), 0x25)
    gdi.SelectObject(hdc, old_f2)

    # ── Erase dynamic region (rings + status) so no ghosting/flicker ──
    scy0 = cy + 62
    rcd = wintypes.RECT(cx - 210, scy0 - 45, cx + 210, scy0 + 115)
    user32.FillRect(hdc, ctypes.byref(rcd), wintypes.HBRUSH(R['brush_bg']))

    # ── Triple-ring spinner ──
    scy = cy + 62
    old_p = gdi.SelectObject(hdc, ctypes.c_void_p(R['pen_ring']))
    t = _splash_tick[0]
    for radius, speed, phase in ((32, 240.0, 0.0), (24, -180.0, 120.0), (16, 360.0, 240.0)):
        st_deg = (speed * t * 0.033 + phase) % 360.0
        st = math.radians(st_deg)
        sx = int(cx + radius * math.cos(st))
        sy = int(scy + radius * math.sin(st))
        p = wintypes.POINT(sx, sy)
        gdi.MoveToEx(hdc, sx, sy, ctypes.byref(p))
        gdi.AngleArc(hdc, float(cx), float(scy), float(radius), st_deg, 270.0)
    gdi.SelectObject(hdc, old_p)

    # ── Status + animated dots ──
    dots = '.' * (1 + (t // 9) % 3)
    old_f3 = gdi.SelectObject(hdc, ctypes.c_void_p(R['font_status']))
    gdi.SetTextColor(hdc, _rgb((0xA0, 0xA0, 0xB0)))
    label = 'Initializing ' + dots
    user32.DrawTextW(hdc, label, -1,
                     ctypes.byref(wintypes.RECT(cx-200, scy+72, cx+200, scy+104)), 0x25)
    gdi.SelectObject(hdc, old_f3)

def _splash_proc(hwnd, msg, wp, lp):
    try:
        if msg == 0x0001:                    # WM_CREATE
            _splash_init_gdi()
            return 0
        if msg == 0x000F:                    # WM_PAINT
            user32 = ctypes.windll.user32
            user32.BeginPaint.restype = wintypes.HDC
            user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]
            user32.EndPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]
            ps = _PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            try:
                if hdc:
                    _splash_draw(hdc, _splash_w[0], _splash_h[0])
            except Exception as e:
                if _paint_err_n[0] < 3:
                    _paint_err_n[0] += 1
                    _trace(f'paint error #{_paint_err_n[0]}: {e!r}')
            finally:
                if hdc:
                    user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == 0x000E:                    # WM_ERASEBKGND — skip (paint fills bg)
            return 1
        if msg == 0x0113:                    # WM_TIMER
            _splash_tick[0] += 1
            _splash_angle[0] = (_splash_angle[0] + 9) % 360
            # Invalidate ONLY the dynamic region (rings + status dots) so the
            # static logo/tagline are never repainted → zero text flicker.
            cx = _splash_w[0] // 2
            scy = _splash_h[0] // 2 + 62
            rc = wintypes.RECT(cx - 210, scy - 45, cx + 210, scy + 115)
            ctypes.windll.user32.InvalidateRect(hwnd, ctypes.byref(rc), False)
            return 0
        if msg == 0x0010:                    # WM_CLOSE
            ctypes.windll.user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:                    # WM_DESTROY
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
    except Exception as e:
        if _paint_err_n[0] < 3:
            _paint_err_n[0] += 1
            _trace(f'proc error: {e!r}')
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wp, lp)

_SPLASH_PROC_REF = _SplashProc(_splash_proc)

def _create_splash():
    global _splash_hwnd
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        user32.RegisterClassExW.restype = ctypes.c_uint16
        user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                           wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, ctypes.c_void_p,
                                           wintypes.HINSTANCE, ctypes.c_void_p]

        class WC(ctypes.Structure):
            _fields_ = [('cbSize', ctypes.c_uint), ('style', ctypes.c_uint),
                        ('lpfnWndProc', ctypes.c_void_p), ('cbClsExtra', ctypes.c_int),
                        ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE),
                        ('hIcon', ctypes.c_void_p), ('hCursor', ctypes.c_void_p),
                        ('hbrBackground', ctypes.c_void_p), ('lpszMenuName', ctypes.c_wchar_p),
                        ('lpszClassName', ctypes.c_wchar_p), ('hIconSm', ctypes.c_void_p)]

        wc = WC()
        wc.cbSize = ctypes.sizeof(WC)
        wc.lpfnWndProc = ctypes.cast(_SPLASH_PROC_REF, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hbrBackground = ctypes.windll.gdi32.CreateSolidBrush(_rgb(BG_RGB))
        wc.lpszClassName = 'CoreFrameSplashCls'
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            return

        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if SAVED_MODE == 'fullscreen':
            x, y, w, h = 0, 0, sw, sh
        else:
            w, h = 1280, 800
            x, y = max(0, (sw-w)//2), max(0, (sh-h)//2)
        _splash_w[0], _splash_h[0] = w, h

        hwnd = user32.CreateWindowExW(
            0x8 | 0x80, 'CoreFrameSplashCls', 'CoreFrame',
            0x80000000 | 0x10000000,   # POPUP | VISIBLE
            x, y, w, h, None, None, kernel32.GetModuleHandleW(None), None)
        if not hwnd:
            return
        _splash_hwnd = hwnd
        user32.SetTimer(hwnd, 1, 33, None)  # ~30 fps spinner

        m = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(m), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(m))
            user32.DispatchMessageW(ctypes.byref(m))
    except Exception:
        pass

if not AUTOSTART_FLAG and not MINIMIZED_FLAG:
    threading.Thread(target=_create_splash, daemon=True, name='splash').start()
_trace('splash thread started')

import urllib.request  # deferred: keep pre-splash boot minimal

def _destroy_splash():
    global _splash_hwnd
    if _splash_hwnd:
        try:
            ctypes.windll.user32.PostMessageW(_splash_hwnd, 0x0010, 0, 0)
        except Exception:
            pass
        _splash_hwnd = None
# ═══════════════ end native splash ═══════════════

from app import start_server  # patches subprocess to hide consoles
_trace('app imported')
import webview.util
import webview
_trace('webview imported')

# Patch interop_dll_path — AV may delete MEIPASS files after extraction
if hasattr(sys, '_MEIPASS'):
    _orig_interop = webview.util.interop_dll_path
    def _patched_interop(dll_name):
        if dll_name in ('win-arm64', 'win-x64', 'win-x86'):
            p = os.path.join(sys._MEIPASS, 'webview', 'lib', 'runtimes', dll_name, 'native')
            if os.path.isdir(p):
                return p
        return _orig_interop(dll_name)
    webview.util.interop_dll_path = _patched_interop

# Log STA-thread init failures (kept from original boot diagnostics)
import webview.platforms.winforms as _wf
_orig_bform_init = _wf.BrowserView.BrowserForm.__init__
def _patched_bform_init(self, window, cache_dir):
    try:
        _orig_bform_init(self, window, cache_dir)
    except Exception:
        log.exception('STA thread init failure (BrowserForm.__init__)')
        raise
_wf.BrowserView.BrowserForm.__init__ = _patched_bform_init

HOST = '127.0.0.1'
PORT = 8420
DATA_DIR = DATA_DIR_EARLY
CONFIG_PATH = os.path.join(DATA_DIR, 'coreframe.json')

if getattr(sys, 'frozen', False):
    STATIC_DIR = os.path.join(sys._MEIPASS, 'static')
else:
    STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'window_mode': SAVED_MODE}

def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)

def _wait_for_server(timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f'http://{HOST}:{PORT}/api/health', timeout=1)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.08)
    return False

def _show_error(title, msg):
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
    except Exception:
        pass

debug_mode = not getattr(sys, 'frozen', False)
threading.Thread(target=start_server,
                 kwargs={'host': HOST, 'port': PORT, 'debug': debug_mode},
                 daemon=True).start()

if not _wait_for_server():
    _trace('server FAILED to start')
    _destroy_splash()
    _show_error("CoreFrame",
        f"CoreFrame failed to start on {HOST}:{PORT}.\n\n"
        "Check the log at:\n" + os.path.join(DATA_DIR, 'coreframe.log'))
    sys.exit(1)
_trace('server ready')
print('[BOOT] Flask ready', flush=True)

config = load_config()
mode = config.get('window_mode', SAVED_MODE)
initial_fullscreen = (mode == 'fullscreen')
initial_frameless = (mode == 'frameless')

COREFRAME_BG = '#0d0d1a'

_trace(f'creating window url=.../?mode={mode} hidden=True')
window = webview.create_window(
    'CoreFrame',
    url=f'http://{HOST}:{PORT}/?mode={mode}',
    width=1280, height=800,
    fullscreen=initial_fullscreen,
    frameless=initial_frameless,
    hidden=True,
    background_color=COREFRAME_BG,
)
_trace('window object created')

_shown = threading.Event()

def _ui(i, WinForms, fn):
    """Run fn on the UI thread WITHOUT risking Invoke-deadlock:
    if caller is already the UI thread, execute directly."""
    try:
        if i.InvokeRequired:
            i.Invoke(WinForms.MethodInvoker(fn))
        else:
            fn()
    except Exception as e:
        _trace(f'_ui error: {e}')

def _try_dark_webview_background(i):
    """Best-effort: set WebView2 control DefaultBackgroundColor to dark."""
    try:
        import System.Drawing as Drawing
        dark = Drawing.ColorTranslator.FromHtml(COREFRAME_BG)
        stack = list(i.Controls)
        while stack:
            c = stack.pop()
            try:
                if c.GetType().Name == 'WebView2':
                    c.DefaultBackgroundColor = dark
                    return True
            except Exception:
                pass
            for ch in c.Controls:
                stack.append(ch)
    except Exception:
        pass
    return False

def _on_loaded():
    """Fires when the app page DOM is ready. NEVER do work inline: pywebview
    may dispatch this on the UI thread — hop to a worker thread immediately."""
    if _shown.is_set():
        return
    _shown.set()
    _trace('loaded event fired — revealing (worker)')
    threading.Thread(target=_do_reveal, daemon=True, name='reveal').start()

def _do_reveal():
    try:
        print('[BOOT] App rendered — revealing', flush=True)

        if AUTOSTART_FLAG or MINIMIZED_FLAG:
            return  # stay hidden; focus_window will reveal later

        # Instant swap: show window, kill splash immediately after.
        try:
            window.show()
        except Exception as e:
            _trace(f'show error: {e}')

        # Pixel-perfect handoff: move splash exactly over the real window
        # (title bar included) so the swap is seamless, then destroy it.
        user32 = ctypes.windll.user32
        hwnd_app = None
        for _ in range(20):  # up to ~1s waiting for native handle
            hwnd_app = user32.FindWindowW(None, 'CoreFrame')
            if hwnd_app:
                break
            time.sleep(0.05)
        if hwnd_app and _splash_hwnd:
            rc = wintypes.RECT()
            if user32.GetWindowRect(hwnd_app, ctypes.byref(rc)):
                SWP_NOACTIVATE = 0x10
                SWP_NOZORDER = 0x4
                user32.SetWindowPos(_splash_hwnd, None,
                                    rc.left, rc.top,
                                    rc.right - rc.left, rc.bottom - rc.top,
                                    SWP_NOACTIVATE | SWP_NOZORDER)

        # Enforce saved window mode natively right now (insurance in case the
        # creation-time styles were deferred while hidden). Serialized via uiq.
        if mode != 'windowed':
            threading.Thread(target=_set_window_mode_impl, args=(mode,),
                             daemon=True, name='mode-enforce').start()

        _destroy_splash()
        _trace('reveal: done')
    except Exception as e:
        _trace(f'_do_reveal exception: {e}')

window.events.loaded += _on_loaded

# WATCHDOG — if `loaded` never fires (pywebview quirk with hidden+url),
# force-reveal so the app can never hang on the splash forever.
def _watchdog():
    if _shown.is_set():
        return
    _shown.set()
    _trace('WATCHDOG: loaded did not fire in 4s — forcing reveal')
    try:
        window.show()
    except Exception:
        pass
    def _force():
        i, WinForms = _get_winform()
        if i:
            try:
                _try_dark_webview_background(i)
            except Exception:
                pass
            _ui(i, WinForms, lambda: setattr(i, 'Opacity', 1.0))
        _destroy_splash()
    threading.Timer(0.2, _force).start()

threading.Timer(4.0, _watchdog).start()

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
        return gui.BrowserView.instances.get(uid), WinForms
    except Exception:
        _winforms_available = False
        return None, None

def set_window_mode(new_mode):
    """js_api entry — offload to worker; never run inline on caller thread."""
    _trace(f'api: set_window_mode {new_mode}')
    threading.Thread(target=_set_window_mode_impl, args=(new_mode,), daemon=True).start()
    return True

def _set_window_mode_impl(new_mode):
    cfg = load_config()
    cfg['window_mode'] = new_mode
    save_config(cfg)
    i, WinForms = _get_winform()
    if not i:
        # No winforms (non-fallback envs): approximate with pywebview window API
        try:
            if new_mode == 'windowed':
                window.restore(); window.resize(1280, 800)
            else:
                window.maximize()
        except Exception as e:
            _trace(f'set_window_mode fallback error: {e}')
        return

    def _apply():
        try:
            _ui_set_mode(i, WinForms, new_mode)
        except Exception as e:
            _trace(f'_ui_set_mode error: {e}')

    # Serialize through the UI worker — never race other WinForms touches
    _post_ui(_apply)

def _ui_set_mode(i, WinForms, new_mode):
    """Runs on the serialized uiq worker. All form mutations are marshaled to
    the real UI thread via BeginInvoke (fire-and-forget, cannot deadlock)."""
    def _mutate():
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
        except Exception as e:
            try:
                _trace(f'_mutate error: {e}')
            except Exception:
                pass
    try:
        i.BeginInvoke(WinForms.MethodInvoker(_mutate))
    except Exception as e:
        try:
            _trace(f'BeginInvoke error: {e}')
        except Exception:
            pass

def minimize_window():
    _trace('api: minimize_window')
    _post_ui(lambda: _safe(lambda: window.minimize()))
    return True

def focus_window():
    _trace('api: focus_window')
    _post_ui(_focus_impl)
    return True

def _safe(fn):
    try:
        fn()
    except Exception as e:
        _trace(f'_safe error: {e}')

def _focus_impl():
    try:
        i, WinForms = _get_winform()
        if not i:
            window.show()
            return
        def _do():
            try:
                if i.WindowState == getattr(WinForms.FormWindowState, 'Minimized'):
                    i.WindowState = getattr(WinForms.FormWindowState, 'Normal')
                i.Opacity = 1.0
                i.BringToFront()
                i.TopMost = True; i.TopMost = False
                i.Focus()
            except Exception as e:
                _trace(f'focus _do error: {e}')
        # We're already on the serialized UI worker → direct call, no Invoke
        if i.InvokeRequired:
            i.Invoke(WinForms.MethodInvoker(_do))
        else:
            _do()
    except Exception as e:
        _trace(f'focus impl error: {e}')

window.expose(set_window_mode, minimize_window, focus_window)

import coreframe.app as _app_mod
def _shutdown():
    try:
        window.destroy()
    except Exception:
        os._exit(0)
_app_mod._shutdown_callback = _shutdown

print('[BOOT] Calling webview.start...', flush=True)
_trace('calling webview.start')
try:
    webview.start(gui='edgechromium', private_mode=False)
    _trace('webview.start returned')
except Exception as e:
    _trace(f'webview.start exception: {e}')
    log.exception('webview.start failed')
    raise