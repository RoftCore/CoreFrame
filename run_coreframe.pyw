import os
import sys
import json
import faulthandler
import threading
import time
import queue as _queue
import ctypes
from ctypes import wintypes
import tempfile
# Earliest possible boot marker: splits bootloader extraction from Python import time.
try:
    with open(os.path.join(tempfile.gettempdir(), 'cf_boot_mark.txt'), 'w') as _bf:
        _bf.write('py %.3f\n' % time.time())
except Exception:
    pass
# Child runners must never flash the bootloader splash (pyi_splash is frozen-only).
if '--ext-runner' in sys.argv:
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass

# ── Single instance: if a server is already alive, bring its window to
# the front and exit. No splash, no second server, no stacked clones.
# Skipped for --ext-runner children (they are not app launches).
if '--ext-runner' not in sys.argv:
    try:
        import urllib.request

        def _single_instance_token():
            try:
                with urllib.request.urlopen(
                        'http://127.0.0.1:8420/api/token',
                        timeout=2) as _resp:
                    return json.loads(_resp.read().decode()).get('token')
            except Exception:
                return None

        if _single_instance_token():
            try:
                _user32 = ctypes.windll.user32
                _kernel32 = ctypes.windll.kernel32

                def _bring_to_front(hwnd):
                    try:
                        if _user32.IsIconic(hwnd):
                            _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                        _user32.ShowWindow(hwnd, 5)  # SW_SHOW
                        _user32.SetForegroundWindow(hwnd)
                        return True
                    except Exception:
                        return False

                _brought = False
                try:
                    _hwnd = _user32.FindWindowW(None, 'CoreFrame')
                    if _hwnd:
                        _brought = _bring_to_front(_hwnd)
                except Exception:
                    pass
                if not _brought:
# Title fallback: any visible top-level window of another CoreFrame.exe (ctypes only).
                    try:
                        _found = []
                        _WINFUNCTYPE = ctypes.WINFUNCTYPE

                        @_WINFUNCTYPE(ctypes.c_bool, wintypes.HWND,
                                      wintypes.LPARAM)
                        def _enum_cb(hwnd, _param):
                            try:
                                if not _user32.IsWindowVisible(hwnd):
                                    return True
                                _pid = wintypes.DWORD()
                                _user32.GetWindowThreadProcessId(
                                    hwnd, ctypes.byref(_pid))
                                if _pid.value == os.getpid():
                                    return True
                                _hproc = _kernel32.OpenProcess(
                                    0x1000, False, _pid.value)
                                if not _hproc:
                                    return True
                                try:
                                    _buf = ctypes.create_unicode_buffer(260)
                                    _size = wintypes.DWORD(260)
                                    _kernel32.QueryFullProcessImageNameW(
                                        _hproc, 0, _buf,
                                        ctypes.byref(_size))
                                    _exe = os.path.basename(
                                        _buf.value or '')
                                finally:
                                    _kernel32.CloseHandle(_hproc)
                                if _exe.lower() == 'coreframe.exe':
                                    _found.append(hwnd)
                            except Exception:
                                pass
                            return True

                        _user32.EnumWindows(_enum_cb, 0)
                        for _hwnd in _found:
                            if _bring_to_front(_hwnd):
                                break
                    except Exception:
                        pass
            except Exception:
                pass
            sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        pass

# ── Embedded ext_runner source (compiled into exe, no MEIPASS files) ───
# GENERATED BLOCK — DO NOT EDIT BY HAND. Edit coreframe/extensions/ext_runner.py
# and run: python tools/sync_ext_runner_source.py. CI fails on drift (--check).
_EXT_RUNNER_SOURCE = r'''
"""
CoreFrame Extension Runner — Subprocess-isolated Python extension executor.

Runs a Python extension in a separate OS process, communicating via JSON-RPC
over stdin/stdout. This provides true security isolation: even if the extension
bypasses Python-level restrictions, the OS process itself is constrained.

Usage:
    python ext_runner.py <config_file>

config_file is a JSON file with:
    - config: the extension config dict
    - ext_path: absolute path to the extension directory
    - restrictions: {level, data_dir, allowed_dirs, blocked_modules, network_allowed}

Security enforced at OS level:
    - File access: only paths under allowed_dirs
    - Network: socket creation blocked if not allowed
    - Subprocess: os.system/subprocess blocked if not allowed
    - Modules: dangerous modules removed from sys.modules before import
"""
import os
import sys
try:
    import orjson as json
    _USE_ORJSON = True
    def _loads(b):
        return json.loads(b)
    def _dumps(o):
        return json.dumps(o).decode()
except ImportError:
    import json
    _USE_ORJSON = False
    def _loads(b):
        return json.loads(b.decode() if isinstance(b, bytes) else b)
    def _dumps(o):
        return json.dumps(o)
import time
import importlib.util
import traceback
import threading

# ── Security Setup (before importing anything else) ────────────────

def _apply_restrictions(restrictions):
    """Apply OS-level security restrictions before loading the extension."""
    level = restrictions.get('level', 0)
    data_dir = restrictions.get('data_dir', '')
    allowed_dirs = restrictions.get('allowed_dirs', [])
    network_allowed = restrictions.get('network_allowed', False)
    subprocess_allowed = restrictions.get('subprocess_allowed', False)
    ext_path = restrictions.get('ext_path', '')

    import builtins
    import stat

    # Store original functions
    _orig_open = builtins.open
    _orig_import = builtins.__import__
    _orig_system = None
    _orig_popen = None

    # ── File access restriction ────────────────────────────────────
    # Build implicit allowlist for runtime internals (exe, MEIPASS, temp, extension dir)
    _implicit_dirs = []
    # exe dir (CoreFrame.exe) and MEIPASS (frozen libs) must always be readable
    try:
        _implicit_dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    _meipass = getattr(sys, '_MEIPASS', None)
    if _meipass:
        _implicit_dirs.append(os.path.abspath(_meipass))
    # Also allow extension's own dir, temp, and runner dir (set later)
    if level < 5:
        def restricted_open(*args, **kwargs):
            path = args[0] if args else kwargs.get('file', '')
            if path:
                path_str = str(path)
                norm_path = os.path.normpath(os.path.abspath(path_str))
                allowed = False
                # Check explicit allowed_dirs (handle '/' meaning any absolute path on Windows)
                for d in allowed_dirs:
                    if d in ('/', '\\', os.sep):
                        if os.path.isabs(norm_path):
                            allowed = True
                            break
                    norm_dir = os.path.normpath(os.path.abspath(d))
                    if norm_path.startswith(norm_dir + os.sep) or norm_path == norm_dir:
                        allowed = True
                        break
                # Allow implicit runtime dirs
                if not allowed:
                    for d in _implicit_dirs:
                        try:
                            nd = os.path.normpath(os.path.abspath(d))
                            if norm_path.startswith(nd + os.sep) or norm_path == nd:
                                allowed = True
                                break
                        except Exception:
                            continue
                # Allow reading the extension's own directory
                norm_ext = os.path.normpath(os.path.abspath(ext_path))
                if norm_path.startswith(norm_ext + os.sep) or norm_path == norm_ext:
                    allowed = True
                # Allow temp files (for IPC)
                tmp_dir = os.path.normpath(os.path.abspath(os.environ.get('TEMP', '')))
                if tmp_dir and norm_path.startswith(tmp_dir + os.sep):
                    allowed = True
                # Allow the ext_runner.py itself
                try:
                    runner_dir = os.path.normpath(os.path.abspath(os.path.dirname(__file__)))
                    if norm_path.startswith(runner_dir + os.sep) or norm_path == runner_dir:
                        allowed = True
                except Exception:
                    pass
                if not allowed:
                    raise PermissionError(
                        f"Security: level {level} cannot access {path_str}"
                    )
            return _orig_open(*args, **kwargs)
        builtins.open = restricted_open

    # ── Network restriction ────────────────────────────────────────
    if not network_allowed:
        import socket as _socket
        _orig_socket = _socket.socket

        class BlockedSocket:
            """Socket replacement that blocks all network operations."""
            def __init__(self, *args, **kwargs):
                raise PermissionError(
                    f"Security: level {level} cannot create network connections"
                )
        _socket.socket = BlockedSocket

        # Also block common HTTP libraries at import level
        _blocked_modules = {'urllib', 'urllib.request', 'urllib.parse',
                           'http.client', 'http.cookiejar'}
        for mod_name in _blocked_modules:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

    # ── Subprocess restriction ─────────────────────────────────────
    if not subprocess_allowed:
        import os as _os
        _orig_system = _os.system
        _orig_popen = _os.popen

        def blocked_system(cmd):
            raise PermissionError(
                f"Security: level {level} cannot run os.system()"
            )
        def blocked_popen(cmd, *args, **kwargs):
            raise PermissionError(
                f"Security: level {level} cannot run os.popen()"
            )
        _os.system = blocked_system
        _os.popen = blocked_popen

        import subprocess as _subprocess
        _orig_run = _subprocess.run
        _orig_popen_class = _subprocess.Popen

        def blocked_run(*args, **kwargs):
            raise PermissionError(
                f"Security: level {level} cannot run subprocess"
            )
        class BlockedPopen:
            """Popen replacement that blocks spawning. Must be a class (not a
            function) so libraries that subclass subprocess.Popen at import
            time (e.g. yt_dlp) still import cleanly; instantiation raises."""
            def __init__(self, *args, **kwargs):
                raise PermissionError(
                    f"Security: level {level} cannot spawn subprocess"
                )
        _subprocess.run = blocked_run
        _subprocess.Popen = BlockedPopen
    else:
        # Allowed but hide console windows on Windows
        if sys.platform.startswith('win'):
            import subprocess as _subprocess
            _CREATE_NO_WINDOW = 0x08000000
            _orig_popen_init2 = _subprocess.Popen.__init__
            def _hidden_init(self, *args, **kwargs):
                kwargs['creationflags'] = kwargs.get('creationflags', 0) | _CREATE_NO_WINDOW
                # Also force STARTUPINFO to hide window if not provided
                if 'startupinfo' not in kwargs or kwargs['startupinfo'] is None:
                    si = _subprocess.STARTUPINFO()
                    si.dwFlags |= _subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = _subprocess.SW_HIDE
                    kwargs['startupinfo'] = si
                return _orig_popen_init2(self, *args, **kwargs)
            _subprocess.Popen.__init__ = _hidden_init

    return restrictions


# ── Extension Loader ───────────────────────────────────────────────

def _load_extension(ext_path, config):
    """Import and instantiate the extension module."""
    ext_id = config.get('id', 'unknown')
    main_file = config.get('main', 'main.py')
    main_path = os.path.join(ext_path, main_file)

    if not os.path.isfile(main_path):
        raise FileNotFoundError(f"Main file not found: {main_path}")

    mod_name = f"ext_isolated_{ext_id}"
    spec = importlib.util.spec_from_file_location(mod_name, main_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to create module spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, 'Extension'):
        raise AttributeError(f"Module has no Extension class")

    return module.Extension(config)


# ── JSON-RPC Server ────────────────────────────────────────────────

def _invoke(fn, params):
    """Call an extension method, adapting to its signature."""
    try:
        import inspect
        sig = inspect.signature(fn)
        if len(sig.parameters) == 0:
            return fn()
        if params:
            return fn(params)
        try:
            return fn(params)
        except TypeError:
            return fn()
    except Exception:
        try:
            return fn(params) if params else fn()
        except TypeError:
            return fn()


def _run_rpc_loop(instance, ext_id, hb_interval=10):
    """
    Main JSON-RPC loop. Reads requests from stdin, calls methods on the
    extension instance, writes responses to stdout.

    Dispatch is concurrent: one reader thread plus a worker pool, correlating
    responses by id as JSON-RPC 2.0 requires. Serving calls in order froze the
    whole child for the duration of the slowest one, so a 0.8s widget call
    timed out behind an 8s call that had nothing to do with it.
    """
    import sys
    import threading
    from concurrent.futures import ThreadPoolExecutor

    _stdout_lock = threading.Lock()

    def safe_write(data):
        try:
            with _stdout_lock:
                sys.stdout.write(data)
                sys.stdout.flush()
        except (BrokenPipeError, OSError):
            # Parent process closed the pipe — we're done
            os._exit(0)

    # Bounded on purpose: a child that can spawn 32 threads can multiply that
    # by every extension. I/O-bound calls still overlap at a handful of workers.
    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='rpc')

    def reply(resp):
        safe_write(_dumps(resp) + '\n')

    def serve(rid, method, params):
        """Run one call in a worker and write its response."""
        try:
            fn = getattr(instance, method, None)
            if fn is None:
                resp = {'error': f'Unknown method: {method}', 'id': rid}
            elif not callable(fn):
                resp = {'result': fn, 'id': rid}
            else:
                resp = {'result': _invoke(fn, params), 'id': rid}
        except Exception as e:
            resp = {'error': f'{type(e).__name__}: {e}', 'id': rid}
        reply(resp)

    # Heartbeat sender
    def heartbeat_loop():
        while True:
            time.sleep(max(hb_interval, 10.0))
            try:
                safe_write(_dumps({'method': 'heartbeat'}) + '\n')
            except Exception:
                break

    hb = threading.Thread(target=heartbeat_loop, daemon=True)
    hb.start()

    try:
        for line in sys.stdin:
            if not line:
                # stdin closed — parent process is gone
                break
            line = line.strip()
            if not line:
                continue
            try:
                req = _loads(line.encode() if isinstance(line, str) else line)
            except Exception as e:
                reply({'error': f'Invalid JSON: {e}', 'id': 0})
                continue

            method = req.get('method', '')
            params = req.get('params', {})
            rid = req.get('id', 0)

            # Heartbeat from coreframe — answered inline, it must not queue
            if method == 'heartbeat':
                reply({'method': 'heartbeat', 'id': rid})
                continue

            # Trivial calls are answered inline in the reader thread, never
            # queued behind slow work. A single pool means a burst of slow
            # calls can occupy every worker; a trivial call waiting behind
            # them then burns its whole budget, the host marks the widget
            # degraded, and after three of those the extension is quarantined
            # for the session — all while the child is healthy and the answer
            # was a dict return away. Only methods that are pure, instant dict
            # returns belong here; anything doing real work stays on the pool.
            if method in ('get_config', 'get_status'):
                try:
                    fn = getattr(instance, method, None)
                    if fn is None or not callable(fn):
                        reply({'error': f'Unknown method: {method}', 'id': rid})
                    else:
                        reply({'result': _invoke(fn, params), 'id': rid})
                except Exception as e:
                    reply({'error': f'{type(e).__name__}: {e}', 'id': rid})
                continue

            # Validate method name (no private methods) before handing it to a worker
            if method.startswith('_'):
                reply({'error': f'Method not allowed: {method}', 'id': rid})
                continue

            pool.submit(serve, rid, method, params)
    except (OSError, IOError):
        # Parent process exited, pipes closed
        pass
    finally:
        # Let in-flight calls finish before on_stop, so a worker is not still
        # inside extension code while the extension tears itself down.
        pool.shutdown(wait=True)
        # Graceful extension shutdown BEFORE interpreter teardown: lets
        # backends stop threads and close handles (e.g. HID) while every
        # module is still alive. Skipping this segfaults C extensions
        # (hid.dll_unloaded) when a daemon thread is inside a C call.
        try:
            stop = getattr(instance, 'on_stop', None)
            if callable(stop):
                stop()
        except Exception:
            pass
        try:
            time.sleep(0.6)
        except Exception:
            pass


# ── Main ───────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: ext_runner.py <config_file>", file=sys.stderr)
        sys.exit(1)

    config_file = sys.argv[1]
    with open(config_file, 'r', encoding='utf-8') as f:
        params = json.load(f)

    config = params.get('config', {})
    ext_path = params.get('ext_path', '')
    restrictions = params.get('restrictions', {})
    ext_id = config.get('id', 'unknown')

    # Apply security restrictions BEFORE loading the extension
    restrictions['ext_path'] = ext_path
    _apply_restrictions(restrictions)

    # Inject coreframe config values into config dict (for extensions that
    # normally import from coreframe.config — in subprocess mode, those
    # modules may not be importable, especially in frozen exe mode)
    coreframe_config = params.get('coreframe_config', {})
    if coreframe_config:
        config['_coreframe'] = coreframe_config

    # Add extension path to sys.path so it can import local modules
    if ext_path not in sys.path:
        sys.path.insert(0, ext_path)

    # Add shared lib dir so extensions can find installed packages (psutil, etc.)
    shared_lib = coreframe_config.get('SHARED_LIB_DIR', '')
    if shared_lib:
        if os.path.isdir(shared_lib) and shared_lib not in sys.path:
            sys.path.insert(0, shared_lib)
        # Windows --prefix installs to Lib/site-packages
        site_pkgs = os.path.join(shared_lib, 'Lib', 'site-packages')
        if os.path.isdir(site_pkgs) and site_pkgs not in sys.path:
            sys.path.insert(0, site_pkgs)
        site_pkgs_unix = os.path.join(shared_lib, 'lib', 'python3.11', 'site-packages')
        if os.path.isdir(site_pkgs_unix) and site_pkgs_unix not in sys.path:
            sys.path.insert(0, site_pkgs_unix)

    # Try to add coreframe parent dir for modules that import coreframe
    # This works in dev mode but not in frozen exe
    coreframe_parent = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if os.path.isdir(os.path.join(coreframe_parent, 'coreframe')):
        if coreframe_parent not in sys.path:
            sys.path.insert(0, coreframe_parent)

    # Load and instantiate the extension
    try:
        instance = _load_extension(ext_path, config)
    except Exception as e:
        resp = {'error': f'Extension load failed: {e}', 'id': 0,
                'traceback': traceback.format_exc()}
        try:
            sys.stdout.write(json.dumps(resp) + '\n')
            sys.stdout.flush()
        except (OSError, IOError, ValueError):
            pass
        sys.exit(1)

    # Send ready signal
    try:
        sys.stdout.write(json.dumps({'result': 'ready', 'id': 0}) + '\n')
        sys.stdout.flush()
    except (OSError, IOError, ValueError):
        sys.exit(0)

    # Run the JSON-RPC loop
    hb_interval = config.get('refresh_interval', 10000) / 1000
    try:
        _run_rpc_loop(instance, ext_id, hb_interval=hb_interval)
    except (OSError, IOError, ValueError):
        pass


if __name__ == '__main__':
    main()
'''

# ── Extension runner mode: CoreFrame.exe --ext-runner <config.json> ──
# Must be checked BEFORE any heavy imports (webview, winforms, etc.)
# We exec() the embedded source directly — no files, no imports, no MEIPASS.
if '--ext-runner' in sys.argv:
    _runner_idx = sys.argv.index('--ext-runner')
    _config_file = sys.argv[_runner_idx + 1] if _runner_idx + 1 < len(sys.argv) else None
    if _config_file:
        sys.argv = [sys.argv[0], _config_file]
        _ns = {'__name__': 'ext_runner', '__file__': 'ext_runner.py'}
        exec(compile(_EXT_RUNNER_SOURCE, 'ext_runner.py', 'exec'), _ns)
        try:
            _ns['main']()
        except (OSError, IOError, ValueError):
            pass
        except SystemExit:
            raise
        except Exception:
            pass
    sys.exit(0)

# DPI Awareness - must be set BEFORE any WinForms/WebView2 initialization
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # fallback for older Windows
    except Exception:
        pass

# Early-boot helpers live in coreframe/host/, bound under their original names.
from coreframe.host import boot as _boot
from coreframe.host import diagnostics as _diag

_start_stack_dumper = lambda: _diag.start_stack_dumper(DATA_DIR_EARLY)
_start_snapshotter = lambda: _diag.start_snapshotter(DATA_DIR_EARLY)
_trace = lambda msg: _boot.trace(log, msg)
_read_mode_early = lambda: _boot.read_mode_early(os.path.join(DATA_DIR_EARLY, 'coreframe.json'))
load_config = lambda: _boot.load_config(CONFIG_PATH, SAVED_MODE)
save_config = lambda cfg: _boot.save_config(CONFIG_PATH, DATA_DIR, cfg)
_wait_for_server = lambda timeout=20: _boot.wait_for_server(HOST, PORT, timeout)
_splash_text = _boot.splash_text
_close_boot_splash = _boot.close_boot_splash
_destroy_splash = _boot.destroy_splash
_show_error = _boot.show_error
_ensure_persistent_runner = lambda: _boot.ensure_persistent_runner(DATA_DIR_EARLY)

# Every WinForms/pythonnet touch goes through this thread; concurrency froze the UI.
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
    try:
        _close_boot_splash()
    except Exception:
        pass
    time.sleep(0.5)
    try:
        import urllib.request
        req = urllib.request.Request('http://127.0.0.1:8420/api/window/focus', method='POST')
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass
    sys.exit(0)

# Single source of truth: coreframe/config.py, cheap because __init__ is lazy (pitfall 39).
try:
    from coreframe.config import DATA_DIR as DATA_DIR_EARLY
except Exception:
    _buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, _buf)
    DATA_DIR_EARLY = os.path.join(_buf.value or os.path.join(os.path.expanduser('~'), 'Documents'), 'CoreFrame')

os.makedirs(DATA_DIR_EARLY, exist_ok=True)
_start_stack_dumper()
_start_snapshotter()


_ensure_persistent_runner()

import logging
LOG_PATH_EARLY = os.path.join(DATA_DIR_EARLY, 'coreframe.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_PATH_EARLY, encoding='utf-8')],
)
log = logging.getLogger('CoreFrame')

_trace('--- launch ---')

# Flags BEFORE importing heavy modules
AUTOSTART_FLAG = '--autostart' in sys.argv or '--minimized' in sys.argv
MINIMIZED_FLAG = '--minimized' in sys.argv

SAVED_MODE = _read_mode_early()

# ── Single boot splash (bootloader) ─────────────────────────────────
# The ONLY loading screen: PyInstaller's bootloader shows splash.png
# (small, centered) during MEIPASS extraction, before any Python runs.
# Progress lines are pushed via pyi_splash.update_text() for loading feel;
# the splash closes exactly once the main window reveals (or earlier on
# autostart/exit paths). pyi_splash exists only in frozen builds.
# Handlers live in coreframe/host/boot.py.

import urllib.request  # deferred: keep pre-splash boot minimal

# Deferred until the splash paints: initializing .NET costs ~1s of black screen.
try:
    import clr
    clr.AddReference('System.Drawing')
    clr.AddReference('System.Windows.Forms')
    from System.Drawing import Point
    from System.Windows.Forms import Timer as WinFormsTimer
except Exception:
    Point = None
    WinFormsTimer = None
_trace('clr imported')
_splash_text('Starting UI...')

from app import start_server  # patches subprocess to hide consoles
_trace('app imported')
_splash_text('Loading application...')

HOST = '127.0.0.1'
PORT = 8420
DATA_DIR = DATA_DIR_EARLY
CONFIG_PATH = os.path.join(DATA_DIR, 'coreframe.json')

if getattr(sys, 'frozen', False):
    STATIC_DIR = os.path.join(sys._MEIPASS, 'static')
else:
    STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

# Boot Flask in parallel with the webview imports below; _wait_for_server needs it up.
debug_mode = not getattr(sys, 'frozen', False)
threading.Thread(target=start_server,
                 kwargs={'host': HOST, 'port': PORT, 'debug': debug_mode},
                 daemon=True, name='flask').start()
_trace('server thread started')

import webview.util
import webview
_trace('webview imported')
_splash_text('Loading view...')

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

# Fix: pywebview's move() passes None for cx/cy, which ctypes rejects (pitfall 20).
_orig_bv_move = _wf.BrowserView.BrowserForm.move
_MOVE_CALLS = 0
def _patched_bv_move(self, x, y):
    global _MOVE_CALLS
    _MOVE_CALLS += 1
    try:
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_SHOWWINDOW = 0x0040
        scale = self._scale
        if scale != 1:
            x_phys = int(x * scale)
            y_phys = int(y * scale)
        else:
            x_phys = int(x)
            y_phys = int(y)
        handle = self.Handle.ToInt32()
        if handle == 0 or handle == -1:
            log.warning('move() called with invalid handle=%s (call #%d, xy=%s,%s)',
                        handle, _MOVE_CALLS, x, y)
            return
        ctypes.windll.user32.SetWindowPos(
            handle, None,
            x_phys, y_phys, 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW
        )
    except Exception:
        log.exception('move() FAILED call #%d: handle=%s, xy=%s,%s, scale=%s',
                      _MOVE_CALLS,
                      getattr(self, 'Handle', 'N/A').ToInt32() if hasattr(getattr(self, 'Handle', None), 'ToInt32') else 'N/A',
                      x, y, getattr(self, '_scale', 'N/A'))
_wf.BrowserView.BrowserForm.move = _patched_bv_move

# At login the disk thrashes: hidden mode retries, manual launches fail fast with a popup.
_server_attempts = 3 if (AUTOSTART_FLAG or MINIMIZED_FLAG) else 1
_server_timeout = 30 if (AUTOSTART_FLAG or MINIMIZED_FLAG) else 20
_server_ok = False
for _attempt in range(_server_attempts):
    if _wait_for_server(timeout=_server_timeout):
        _server_ok = True
        break
    _trace(f'server wait attempt {_attempt + 1}/{_server_attempts} timed out, retrying...')
if not _server_ok:
    _trace('server FAILED to start')
    _destroy_splash()
    if not (AUTOSTART_FLAG or MINIMIZED_FLAG):
        _show_error("CoreFrame",
            f"CoreFrame failed to start on {HOST}:{PORT}.\n\n"
            "Check the log at:\n" + os.path.join(DATA_DIR, 'coreframe.log'))
    else:
        _trace('autostart: silent exit, no popup at login')
    sys.exit(1)
_trace('server ready')
print('[BOOT] Flask ready', flush=True)
if MINIMIZED_FLAG:
    # Hidden (tray) mode: nothing else closes the splash. --autostart boots visible.
    _close_boot_splash()
else:
    _splash_text('Opening window...')

config = load_config()
mode = config.get('window_mode', SAVED_MODE)
initial_fullscreen = (mode == 'fullscreen')
initial_frameless = (mode == 'frameless')
# Live mode; _focus_impl re-asserts Maximized after minimize/restore.
_current_mode = mode

COREFRAME_BG = '#0d0d1a'

_trace(f'creating window url=.../?mode={mode} hidden=True')
# NEVER frameless=True at creation: it wedges WebView2 so `loaded` never fires (pitfall 23).
window = webview.create_window(
    'CoreFrame',
    url=f'http://{HOST}:{PORT}/?mode={mode}',
    width=1280, height=800,
    fullscreen=initial_fullscreen,
    frameless=False,
    easy_drag=False,
    hidden=True,
    background_color=COREFRAME_BG,
)
_trace('window object created')

# ── Tray icon (hidden mode only) ─────────────────────────────────────
# This is THE visual indicator that CoreFrame is running with the window
# hidden (autostart / minimized): tooltip states the mode, double-click
# restores the window, and the menu offers Open + graceful Exit.
# Created on the main thread before webview.start() runs its loop there,
# so NotifyIcon events dispatch normally. Everything guarded: tray must
# never break boot.
_tray_icon = None

def _setup_tray():
    global _tray_icon
    if not (AUTOSTART_FLAG or MINIMIZED_FLAG):
        return
# CRITICAL: the tray needs its own STA thread; WinForms before webview.start() breaks it.
    try:
        import System.Threading as ST
        import System.Windows.Forms as WinForms
        import System.Drawing as Drawing

        def _tray_thread_main():
            ni_local = None
            try:
                try:
                    icon = Drawing.Icon.ExtractAssociatedIcon(sys.executable)
                except Exception:
                    icon = Drawing.SystemIcons.Application
                ni_local = WinForms.NotifyIcon()
                ni_local.Icon = icon
                ni_local.Visible = True
# AUTOSTART_FLAG is also true for --minimized, so test that one first.
                if MINIMIZED_FLAG:
                    ni_local.Text = 'CoreFrame \u2014 minimizado'
                else:
                    ni_local.Text = 'CoreFrame \u2014 inicio autom\u00e1tico activo'
                ni_local.BalloonTipTitle = 'CoreFrame'
                ni_local.BalloonTipText = 'Running in background. Double-click to open.'
                try:
                    ni_local.ShowBalloonTip(3000)
                except Exception:
                    pass

                def _tray_open(_s=None, _e=None):
                    try:
                        _post_ui(_focus_impl)
                    except Exception:
                        pass

                def _tray_exit(_s=None, _e=None):
                    try:
                        ni_local.Visible = False
                        ni_local.Dispose()
                    except Exception:
                        pass
                    # Graceful quit through the backend (stops server + extensions).
                    try:
                        import urllib.request as _urlreq
                        from coreframe.auth import get_token as _get_token
                        _req = _urlreq.Request(
                            f'http://{HOST}:{PORT}/api/quit', method='POST',
                            headers={'X-CoreFrame-Token': _get_token()},
                            data=b'{}')
                        _urlreq.urlopen(_req, timeout=10)
                    except Exception:
                        pass
                    try:
                        os._exit(0)
                    except Exception:
                        pass

                ni_local.DoubleClick += _tray_open
                menu = WinForms.ContextMenuStrip()
                mi_open = WinForms.ToolStripMenuItem('Open')
                mi_open.Click += _tray_open
                mi_exit = WinForms.ToolStripMenuItem('Exit')
                mi_exit.Click += _tray_exit
                menu.Items.Add(mi_open)
                menu.Items.Add(mi_exit)
                ni_local.ContextMenuStrip = menu
                global _tray_icon
                _tray_icon = ni_local
                _trace('tray icon ready (hidden mode)')
                WinForms.Application.Run()
            except Exception as e:
                _trace(f'tray thread failed (non-fatal): {e}')
                try:
                    if ni_local is not None:
                        ni_local.Visible = False
                        ni_local.Dispose()
                except Exception:
                    pass

        t = ST.Thread(ST.ThreadStart(_tray_thread_main))
        t.IsBackground = True
        t.SetApartmentState(ST.ApartmentState.STA)
        t.Start()
    except Exception as e:
        _trace(f'tray setup failed (non-fatal): {e}')

_setup_tray()

_shown = threading.Event()
_frameless_ok = False
# Geometry applied at boot or by the user; focus_window checks it before maximizing.
_boot_mode_applied = False

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

def _apply_initial_frameless():
    """Apply frameless + maximize at startup.  Safe to call multiple times.
    Retries up to 2s waiting for the WinForms form to become available —
    pywebview may not have registered it in BrowserView.instances yet.
    Uses the EXACT same logic as _ui_set_mode (BeginInvoke, center then
    maximize) — that path is proven to work."""
    i, WinForms = None, None
    for attempt in range(10):
        i, WinForms = _get_winform()
        if i:
            break
        time.sleep(0.2)
    if not i:
        _trace('_apply_initial_frameless: form not available after 2s, skipping')
        return
    def _mutate():
        try:
            screen = WinForms.Screen.FromHandle(i.Handle)
            # Identical logic to _ui_set_mode 'frameless' branch
            i.FormBorderStyle = getattr(WinForms.FormBorderStyle, 'None')
            i.WindowState = getattr(WinForms.FormWindowState, 'Normal')
            sw, sh = screen.Bounds.Width, screen.Bounds.Height
            fw, fh = i.Width, i.Height
            if fw == 0 or fh == 0:
                fw, fh = 1280, 800
            if Point:
                i.Location = Point((sw - fw) // 2, (sh - fh) // 2)
            else:
                i.Location = WinForms.Point((sw - fw) // 2, (sh - fh) // 2)
            i.WindowState = getattr(WinForms.FormWindowState, 'Maximized')
            i.TopMost = False
            _start_frameless_taskbar_watcher(i, screen)
            global _frameless_ok, _boot_mode_applied
            _frameless_ok = True
            _boot_mode_applied = True
            _trace('initial frameless applied successfully')
        except Exception as e:
            _trace(f'initial frameless _mutate error: {e}')
    try:
        i.BeginInvoke(WinForms.MethodInvoker(_mutate))
    except Exception as e:
        _trace(f'initial frameless BeginInvoke error: {e}')

def _do_reveal():
    try:
        print('[BOOT] App rendered — revealing', flush=True)

        if MINIMIZED_FLAG:
            return  # stay hidden; focus_window will reveal later

        # Show window, then close the single boot splash.
        try:
            window.show()
        except Exception as e:
            _trace(f'show error: {e}')

        _close_boot_splash()
        _trace('reveal: done')

        # Invoke (not BeginInvoke) here: we are on a worker thread, so this blocks only it.
        if initial_frameless:
            _apply_initial_frameless()
# Safety-net: re-apply after 1s in case late layout processing overrode it.
            def _frameless_timer():
                if not _frameless_ok:
                    _apply_initial_frameless()
            threading.Timer(1.0, _frameless_timer).start()
    except Exception as e:
        _trace(f'_do_reveal exception: {e}')

window.events.loaded += _on_loaded

# WATCHDOG: `loaded` never fires with hidden+url, so force-reveal to avoid a stuck splash.
def _watchdog():
    if _shown.is_set():
        return
    _shown.set()
    _trace('WATCHDOG: loaded did not fire in 4s — forcing reveal')
# Never pop a window in minimized mode; _destroy_splash is idempotent.
    if MINIMIZED_FLAG:
        _trace('WATCHDOG: hidden mode, keeping window hidden')
        _destroy_splash()
        return
    try:
        window.show()
    except Exception:
        pass
    def _force():
        i, WinForms = _get_winform()
        if i:
# NEVER touch the STA synchronously here: it is wedged on this path (pitfall 25).
            try:
                i.BeginInvoke(WinForms.MethodInvoker(
                    lambda: _try_dark_webview_background(i)))
            except Exception:
                pass
            try:
                i.BeginInvoke(WinForms.MethodInvoker(
                    lambda: setattr(i, 'Opacity', 1.0)))
            except Exception:
                pass
        _destroy_splash()
        # Apply frameless if the app started in frameless mode
        if initial_frameless:
            _apply_initial_frameless()
            def _frameless_timer_watchdog():
                if not _frameless_ok:
                    _apply_initial_frameless()
            threading.Timer(1.0, _frameless_timer_watchdog).start()
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
    global _boot_mode_applied, _current_mode
    _boot_mode_applied = True  # manual control wins over any later boot apply
    _current_mode = new_mode
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
                i.WindowState = getattr(WinForms.FormWindowState, 'Maximized')
                i.Bounds = screen.Bounds
                i.TopMost = True
            elif new_mode == 'frameless':
                i.FormBorderStyle = getattr(WinForms.FormBorderStyle, 'None')
                # Explicit centering for frameless: set Normal first, then center, then Maximized
                i.WindowState = getattr(WinForms.FormWindowState, 'Normal')
                sw, sh = screen.Bounds.Width, screen.Bounds.Height
                fw, fh = i.Width, i.Height
                if fw == 0 or fh == 0:
                    fw, fh = 1280, 800
                if Point:
                    i.Location = Point((sw - fw) // 2, (sh - fh) // 2)
                else:
                    i.Location = WinForms.Point((sw - fw) // 2, (sh - fh) // 2)
                i.WindowState = getattr(WinForms.FormWindowState, 'Maximized')
                i.TopMost = False
                # Start timer to auto-adjust for auto-hidden taskbar
                _start_frameless_taskbar_watcher(i, screen)
            else:
                # windowed: restore normal border, normal state, and reasonable size
                i.FormBorderStyle = WinForms.FormBorderStyle.Sizable
                i.WindowState = getattr(WinForms.FormWindowState, 'Normal')
                i.TopMost = False
                i.Size = WinForms.Size(1280, 800)
                sw, sh = screen.Bounds.Width, screen.Bounds.Height
                if Point:
                    i.Location = Point((sw - 1280) // 2, (sh - 800) // 2)
                else:
                    i.Location = WinForms.Point((sw - 1280) // 2, (sh - 800) // 2)
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

def _start_frameless_taskbar_watcher(i, screen):
    """Periodic timer to re-adjust frameless bounds when taskbar auto-hides/shows."""
    try:
        last_wa = screen.WorkingArea
        def _check():
            nonlocal last_wa
            try:
                if not i.IsHandleCreated or i.IsDisposed:
                    return
                current_wa = screen.WorkingArea
                if current_wa != last_wa:
                    last_wa = current_wa
                    # Re-apply bounds to match new WorkingArea
                    if current_wa == screen.Bounds:
                        # Taskbar hidden → full screen
                        i.Bounds = screen.Bounds
                    else:
                        # Taskbar visible → leave space
                        i.Bounds = current_wa
            except Exception:
                pass
        timer = WinFormsTimer() if WinFormsTimer else System.Windows.Forms.Timer()
        timer.Interval = 1000  # check every 1s
        timer.Tick += lambda s, e: _check()
        timer.Start()
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
# Hidden/autostart windows need an explicit show: BringToFront never unhides them.
                try:
                    i.Show()
                except Exception:
                    pass
                if i.WindowState == getattr(WinForms.FormWindowState, 'Minimized'):
                    i.WindowState = getattr(WinForms.FormWindowState, 'Normal')
                i.Opacity = 1.0
                i.BringToFront()
                i.TopMost = True; i.TopMost = False
                i.Focus()
# First reveal from hidden/autostart skipped the boot geometry step: apply it once.
                global _boot_mode_applied
                if not _boot_mode_applied and (initial_frameless or initial_fullscreen):
                    _boot_mode_applied = True
                    if initial_frameless:
                        _apply_initial_frameless()
                    else:
                        try:
                            _ui_set_mode(i, WinForms, 'fullscreen')
                        except Exception as _e:
                            _trace(f'focus initial fullscreen error: {_e}')
# Minimize/restore resets WindowState to Normal: re-assert the mode on the UI thread.
                try:
                    _cm = globals().get('_current_mode', '')
                    if _cm == 'fullscreen':
                        i.TopMost = True
                    if _cm in ('frameless', 'fullscreen'):
                        if i.WindowState != getattr(WinForms.FormWindowState, 'Maximized'):
                            i.WindowState = getattr(WinForms.FormWindowState, 'Maximized')
                except Exception as _e2:
                    _trace(f'focus ensure-maximized error: {_e2}')
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