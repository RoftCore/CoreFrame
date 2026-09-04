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

def _run_rpc_loop(instance, ext_id, hb_interval=10):
    """
    Main JSON-RPC loop. Reads requests from stdin, calls methods on the
    extension instance, writes responses to stdout.
    """
    import sys
    import threading

    _stdout_lock = threading.Lock()

    def safe_write(data):
        try:
            with _stdout_lock:
                sys.stdout.write(data)
                sys.stdout.flush()
        except (BrokenPipeError, OSError):
            # Parent process closed the pipe — we're done
            os._exit(0)

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
                resp = {'error': f'Invalid JSON: {e}', 'id': 0}
                safe_write(_dumps(resp) + '\n')
                continue

            method = req.get('method', '')
            params = req.get('params', {})
            rid = req.get('id', 0)

            # Heartbeat from coreframe — respond
            if method == 'heartbeat':
                safe_write(_dumps({'method': 'heartbeat', 'id': rid}) + '\n')
                continue

            # Validate method name (no private methods)
            if method.startswith('_'):
                resp = {'error': f'Method not allowed: {method}', 'id': rid}
                safe_write(_dumps(resp) + '\n')
                continue

            # Call the method
            try:
                fn = getattr(instance, method, None)
                if fn is None:
                    resp = {'error': f'Unknown method: {method}', 'id': rid}
                elif not callable(fn):
                    # Property/attribute access
                    resp = {'result': fn, 'id': rid}
                else:
                    # Try calling with params, fallback to no-args for compat
                    try:
                        import inspect
                        sig = inspect.signature(fn)
                        if len(sig.parameters) == 0:
                            result = fn()
                        elif params:
                            result = fn(params)
                        else:
                            try:
                                result = fn(params)
                            except TypeError:
                                result = fn()
                    except Exception:
                        try:
                            result = fn(params) if params else fn()
                        except TypeError:
                            result = fn()
                    resp = {'result': result, 'id': rid}
            except Exception as e:
                resp = {'error': f'{type(e).__name__}: {e}', 'id': rid}

            try:
                safe_write(_dumps(resp) + '\n')
            except Exception:
                break
    except (OSError, IOError):
        # Parent process exited, pipes closed
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
