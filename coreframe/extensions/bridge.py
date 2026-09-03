import os
import sys
import json as _stdjson
try:
    import orjson as _orjson
    _USE_ORJSON = True
    def _json_dumps(o): return _orjson.dumps(o).decode()
    def _json_loads(s): return _orjson.loads(s if isinstance(s, (bytes, bytearray)) else s.encode() if isinstance(s, str) else s)
    def _json_load(f): return _orjson.loads(f.read())
except ImportError:
    _USE_ORJSON = False
    def _json_dumps(o): return _stdjson.dumps(o)
    def _json_loads(s): return _stdjson.loads(s)
    def _json_load(f): return _stdjson.load(f)
import time
import tempfile
import threading
import subprocess as _subprocess
import json as json  # keep stdlib json for .dump/.load file ops (orjson has no dump)

from coreframe.config import log

# Force no console windows on any subprocess
if sys.platform.startswith('win'):
    import ctypes
    _CREATE_NO_WINDOW = 0x08000000
    _DETACHED_PROCESS = 0x00000008
    _orig_init = _subprocess.Popen.__init__
    def _patched_init(self, *args, **kwargs):
        old = kwargs.get('creationflags', 0)
        kwargs['creationflags'] = old | _CREATE_NO_WINDOW | _DETACHED_PROCESS
        return _orig_init(self, *args, **kwargs)
    _subprocess.Popen.__init__ = _patched_init
subprocess = _subprocess


# ── UAC Elevation ─────────────────────────────────────────────────
# Methods that INHERENTLY require admin (always need elevation).
# bash/exec/system_command are NOT here — they run at user level and only
# need elevation if the specific command fails (the extension handles that).
_ADMIN_METHODS = {
    'registry_write', 'service_control', 'adapter_control',
    'delete_file',
}


def _get_helper_path():
    """Find coreframe_helper.exe next to the main executable."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    # Go up from coreframe/extensions/ to project root
    if not getattr(sys, 'frozen', False):
        base = os.path.dirname(os.path.dirname(base))
    return os.path.join(base, 'coreframe_helper.exe')


def _call_elevated(method, params, timeout=30):
    """Execute an admin operation by launching coreframe_helper.exe with UAC elevation.

    Uses ShellExecuteW("runas") to trigger the Windows UAC prompt for a
    separate helper process. The helper reads the operation from a temp file
    and writes the result to another temp file.
    """
    if not sys.platform.startswith('win'):
        return {'error': 'Elevation only supported on Windows'}

    helper = _get_helper_path()
    if not os.path.isfile(helper):
        return {'error': f'Helper not found: {helper}'}

    tmp_dir = tempfile.gettempdir()
    ts = int(time.time() * 1000)
    op_file = os.path.join(tmp_dir, f'coreframe_op_{ts}.json')
    result_file = os.path.join(tmp_dir, f'coreframe_result_{ts}.json')

    op_data = {'type': method, 'params': params or {}}
    with open(op_file, 'w', encoding='utf-8') as f:
        json.dump(op_data, f)

    try:
        result = _elevated_run(helper, op_file, result_file, timeout)
    except Exception as e:
        result = {'error': f'Elevation failed: {e}'}
    finally:
        for p in (op_file, result_file):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    return result


def _elevated_run(helper_path, op_file, result_file, timeout):
    """Launch helper.exe with ShellExecuteW('runas') and wait for result."""
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    INFINITE = 0xFFFFFFFF

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ('cbSize', ctypes.c_ulong),
            ('fMask', ctypes.c_ulong),
            ('hwnd', ctypes.c_void_p),
            ('lpVerb', ctypes.c_wchar_p),
            ('lpFile', ctypes.c_wchar_p),
            ('lpParameters', ctypes.c_wchar_p),
            ('lpDirectory', ctypes.c_wchar_p),
            ('nShow', ctypes.c_int),
            ('hInstApp', ctypes.c_void_p),
            ('lpIDList', ctypes.c_void_p),
            ('lpClass', ctypes.c_wchar_p),
            ('hkeyClass', ctypes.c_void_p),
            ('dwHotKey', ctypes.c_ulong),
            ('hIconOrMonitor', ctypes.c_void_p),
            ('hProcess', ctypes.c_void_p),
        ]

    params = f'"{op_file}" "{result_file}"'
    sei = SHELLEXECUTEINFO()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFO)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = 'runas'
    sei.lpFile = helper_path
    sei.lpParameters = params
    sei.nShow = 0  # SW_HIDE

    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = kernel32.GetLastError()
        # ERROR_CANCELLED = 1223 (user clicked No on UAC)
        if err == 1223:
            return {'error': 'UAC denied by user'}
        return {'error': f'ShellExecuteExW failed: error {err}'}

    h_process = sei.hProcess

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(result_file):
            time.sleep(0.1)
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                kernel32.CloseHandle(h_process)
                return result
            except (json.JSONDecodeError, OSError):
                pass
        # Check if process exited
        exit_code = kernel32.WaitForSingleObject(h_process, 100)
        if exit_code != 258:  # WAIT_TIMEOUT
            break
        # Process exited, try to read result one more time
        if os.path.exists(result_file):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                kernel32.CloseHandle(h_process)
                return result
            except (json.JSONDecodeError, OSError):
                pass
            break

    kernel32.CloseHandle(h_process)
    return {'error': f'Helper timed out after {timeout}s'}


# Methods that require escalation when called via bridge
_BRIDGE_ESCALATION_METHODS = {
    'bash', 'exec', 'system_command',
    'write_file', 'edit_file', 'replace_file', 'delete_file',
    'registry_write', 'service_control', 'adapter_control',
    'list_dir', 'read_file',
}


class SubprocessBridge:
    """JSON-RPC bridge for multi-language extensions (node, python subprocess)."""

    _LANG_MAP = {
        'node': 'node',
        'nodejs': 'node',
        'javascript': 'node',
        'python': sys.executable,
        'py': sys.executable,
    }

    def __init__(self, config, ext_path, ext_isolation):
        self.ext_id = config.get('id', '?')
        self.language = config.get('language', 'python')
        self.main = config.get('main', 'main.py')
        self.config = config
        self._proc = None
        self._lock = threading.Lock()
        self._reader_lock = threading.Lock()
        self._read_buffer = {}
        self._running = True
        self._started = False
        self._start_time = 0.0
        self._ext_isolation = ext_isolation
        self._config_file = None  # Temp config file for isolated mode
        self._start(ext_path)

    def _start(self, ext_path):
        main_path = os.path.join(ext_path, self.main)
        if not os.path.isfile(main_path):
            raise FileNotFoundError(f"Main file not found: {main_path}")

        interpreter = self._LANG_MAP.get(self.language)
        if not interpreter:
            raise RuntimeError(f"Unsupported language: {self.language}")

        # ── Isolated mode: use ext_runner.py ──────────────────────
        if self.config.get('isolated', False) and self.language in ('python', 'py'):
            cmd = self._start_isolated(ext_path, interpreter)
        else:
            cmd = [interpreter, main_path]

        startupinfo = None
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ext_path,
            text=True,
            bufsize=1,
            startupinfo=startupinfo,
        )
        self._started = True
        self._start_time = time.monotonic()
        log.info("[Bridge] Started %s process for %s (pid=%d)", self.language, self.ext_id, self._proc.pid)
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name=f'bridge-{self.ext_id}')
        self._reader.start()

        # For isolated mode: wait for "ready" signal from runner
        if self.config.get('isolated', False) and self.language in ('python', 'py'):
            self._wait_for_ready()

        # Start heartbeat sender for subprocess extensions
        if self.language not in ('python', 'py'):
            self._hb_thread = threading.Thread(target=self._heartbeat_sender, daemon=True, name=f'bridge-hb-{self.ext_id}')
            self._hb_thread.start()

    def _wait_for_ready(self, timeout=15):
        """Wait for the runner's 'ready' signal after startup."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                err = self._proc.stderr.read() if self._proc.stderr else ''
                raise RuntimeError(f"Runner process died during startup: {err}")
            with self._reader_lock:
                resp = self._read_buffer.pop(0, None)
            if resp is not None:
                if 'error' in resp:
                    raise RuntimeError(f"Runner startup failed: {resp['error']}")
                log.info("[Bridge] Runner ready for %s", self.ext_id)
                return
            time.sleep(0.01)
        raise RuntimeError(f"Runner for {self.ext_id} did not become ready within {timeout}s")

    def _start_isolated(self, ext_path, interpreter):
        """Create temp config file and return cmd for ext_runner.

        In frozen mode, the exe itself acts as the runner via --ext-runner flag.
        In dev mode, ext_runner.py is invoked as a separate Python script.
        """
        # Find runner: in dev mode, ext_runner.py is next to this file
        if not getattr(sys, 'frozen', False):
            runner_path = os.path.join(os.path.dirname(__file__), 'ext_runner.py')
            if not os.path.isfile(runner_path):
                raise FileNotFoundError(f"Runner not found: {runner_path}")

        restrictions = self._build_restrictions()

        # Pass coreframe config values so the extension can access them
        from coreframe.config import DATA_DIR, SHARED_LIB_DIR, DATA_DATA_DIR
        coreframe_config = {
            'DATA_DIR': DATA_DIR,
            'SHARED_LIB_DIR': SHARED_LIB_DIR,
            'DATA_DATA_DIR': DATA_DATA_DIR,
        }

        params = {
            'config': self.config,
            'ext_path': ext_path,
            'restrictions': restrictions,
            'coreframe_config': coreframe_config,
        }

        # Write config to temp file
        tmp_dir = tempfile.gettempdir()
        ts = int(time.time() * 1000)
        self._config_file = os.path.join(tmp_dir, f'ext_cfg_{self.ext_id}_{ts}.json')
        with open(self._config_file, 'w', encoding='utf-8') as f:
            json.dump(params, f, ensure_ascii=False)

        log.info("[Bridge] Isolated mode for %s (restrictions: level=%s, network=%s)",
                 self.ext_id, restrictions.get('level'), restrictions.get('network_allowed'))
        if getattr(sys, 'frozen', False):
            return [sys.executable, '--ext-runner', self._config_file]
        return [interpreter, runner_path, self._config_file]

    @staticmethod
    def _find_system_python():
        """Find a usable system Python with pip-installed packages."""
        import shutil
        # Try PATH first
        found = shutil.which('python')
        if found:
            return found
        # Common Windows install paths
        for candidate in [
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Python', 'Python311', 'python.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Python', 'Python312', 'python.exe'),
            r'C:\Python311\python.exe',
            r'C:\Python312\python.exe',
        ]:
            if candidate and os.path.isfile(candidate):
                return candidate
        return None

    def _build_restrictions(self):
        """Build restrictions dict from extension config."""
        from coreframe.config import DATA_DIR, SHARED_LIB_DIR

        perms = self.config.get('permissions', {})
        level_val = perms.get('level', 0)
        if isinstance(level_val, int):
            level = level_val
        else:
            level = {'basic': 0, 'storage': 1, 'user_files': 2,
                     'network': 3, 'system': 4, 'admin': 5}.get(str(level_val).lower(), 0)

        data_dir = self.config.get('data_dir', '')
        ext_id = self.config.get('id', '')

        # Build allowed directories list
        allowed_dirs = []
        if level >= 5:
            # Admin: everything allowed
            allowed_dirs = ['/']
        elif level >= 4:
            # System: everything except consent files
            allowed_dirs = ['/']
        elif level >= 3:
            # Network: read-only, own data_dir only
            allowed_dirs = [data_dir]
        elif level >= 2:
            # User files: mediated
            allowed_dirs = [data_dir, DATA_DIR]
        elif level >= 1:
            # Storage: own data_dir only
            allowed_dirs = [data_dir]
        else:
            # Basic: nothing
            allowed_dirs = []

        return {
            'level': level,
            'data_dir': data_dir,
            'allowed_dirs': allowed_dirs,
            'network_allowed': level >= 3,
            'subprocess_allowed': level >= 4,
        }

    def _heartbeat_sender(self):
        while self._running and self._proc and self._proc.poll() is None:
            time.sleep(10.0)
            if not self._running or not self._proc or self._proc.poll() is not None:
                break
            try:
                with self._lock:
                    self._proc.stdin.write(_json_dumps({'method': 'heartbeat'}) + '\n')
                    self._proc.stdin.flush()
            except Exception:
                break

    def _read_loop(self):
        while self._running and self._proc and self._proc.poll() is None:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                data = _json_loads(line)
                # Proactive heartbeat from runner (no id field) — update health
                if data.get('method') == 'heartbeat' and 'id' not in data:
                    self._ext_isolation.heartbeat(self.ext_id)
                    continue
                rid = data.get('id')
                if rid is not None:
                    with self._reader_lock:
                        self._read_buffer[rid] = data
            except (ValueError, OSError, Exception):
                pass
        # Process exited — read any remaining stderr
        if self._proc:
            try:
                err = self._proc.stderr.read() if self._proc.poll() is not None else ''
                if err:
                    log.warning("[Bridge] %s stderr: %s", self.ext_id, err.strip())
            except Exception:
                pass
        err = self._proc.stderr.read() if self._proc and self._proc.poll() is not None else ''
        if err:
            log.warning("[Bridge] %s stderr: %s", self.ext_id, err.strip())

    def _call(self, method, params=None):
        if not self._proc or self._proc.poll() is not None:
            raise RuntimeError(f"Extension {self.ext_id} process is dead")

        # ── Permission check for bridge methods ────────────────────
        if method in _BRIDGE_ESCALATION_METHODS:
            from coreframe.extensions.permissions import get_permission_manager, ESCALATION_METHODS
            perm = get_permission_manager()
            required_level = ESCALATION_METHODS.get(method, 5)
            # Check base level first
            if not perm.check(self.ext_id, required_level):
                perm.emit_escalation_request(
                    self.ext_id,
                    self.config.get('name', self.ext_id),
                    method,
                    required_level,
                )
                return {'error': f'Permission denied: {method} requires {required_level}'}
            # Check if escalation is granted
            if not perm.check_escalation(self.ext_id, method):
                perm.emit_escalation_request(
                    self.ext_id,
                    self.config.get('name', self.ext_id),
                    method,
                    required_level,
                )
                return {'error': f'Escalation denied: {method}'}

        # ── Admin methods → elevated helper.exe with UAC ───────────
        if method in _ADMIN_METHODS:
            return _call_elevated(method, params)

        rid = int(time.time() * 1000) % 1000000 + id(method) % 1000
        req = _json_dumps({'method': method, 'params': params or {}, 'id': rid}) + '\n'

        with self._lock:
            self._proc.stdin.write(req)
            self._proc.stdin.flush()

        is_data_fetch = method in ('get_config','get_entries','get_status','get_cpu','get_ram','get_gpu','get_disk','get_fortune','get_notes','get_ping')
        timeout = 0.8 if is_data_fetch else 30
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._reader_lock:
                resp = self._read_buffer.pop(rid, None)
            if resp is not None:
                if 'error' in resp:
                    return {'error': resp['error']}
                result = resp.get('result', resp)
                if isinstance(result, dict):
                    return result
                return {'value': result}
            time.sleep(0.01)

        # Timeout -> widget en degradado, no bloquea CoreFrame
        try:
            h = self._ext_isolation.health.get(self.ext_id) if hasattr(self, '_ext_isolation') and self._ext_isolation else None
            if h:
                h.error_count = getattr(h, 'error_count', 0) + 1
                if h.error_count >= 3:
                    h.status = 'degraded'
        except Exception:
            pass
        return {'error': f'Timeout: {method} no responde ({timeout}s) — widget en degradado'}

    def __getattr__(self, name):
        if name.startswith('_') or name in ('start', 'on_stop', 'stop', 'config', 'ext_id'):
            raise AttributeError(name)
        def caller(params=None):
            return self._call(name, params)
        return caller

    def on_stop(self):
        self._running = False
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        # Clean up temp config file
        if self._config_file and os.path.exists(self._config_file):
            try:
                os.remove(self._config_file)
            except OSError:
                pass

    def heartbeat(self):
        try:
            return self._call('heartbeat', {})
        except Exception:
            return {'error': 'Heartbeat failed'}
