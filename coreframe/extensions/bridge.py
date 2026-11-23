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
from coreframe.extensions.bridge_elevation import _ADMIN_METHODS, call_elevated

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



# Methods that require escalation when called via bridge
_BRIDGE_ESCALATION_METHODS = {
    'bash', 'exec', 'system_command',
    'write_file', 'edit_file', 'replace_file', 'delete_file',
    'registry_write', 'service_control', 'adapter_control',
    'list_dir', 'read_file',
}


class SubprocessBridge:
    """JSON-RPC bridge for multi-language extensions (node, python subprocess)."""

    # Every spawned child registers here so the drain can reap orphans (pitfall 26).
    _live_children = set()
    _live_lock = threading.Lock()

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
        # The caller waits here instead of spinning on the buffer every 10 ms (pitfall 49).
        self._resp_cv = threading.Condition(self._reader_lock)
        self._read_buffer = {}
        # Monotonic request ids: time-derived ones collided in _read_buffer under concurrency.
        self._rid_seq = 0
        self._running = True
        self._started = False
        self._start_time = 0.0
        self._last_call = 0.0
        self._ext_isolation = ext_isolation
        self._config_file = None  # Temp config file for isolated mode
        try:
            self._start(ext_path)
        except Exception:
            try:
                self.on_stop()
            except Exception:
                pass
            raise

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

        # Pin UTF-8 on both ends: the child writes the ANSI codepage, so every non-ASCII char arrived as U+FFFD.
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ext_path,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            startupinfo=startupinfo,
        )
        with SubprocessBridge._live_lock:
            SubprocessBridge._live_children.add(self._proc)
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

    def _wait_for_ready(self, timeout=30):
        """Wait for the child's ready line, failing fast if it died meanwhile."""
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
                log.debug("[Bridge] Runner ready for %s", self.ext_id)
                return
            time.sleep(0.01)
        raise RuntimeError(f"Runner for {self.ext_id} did not become ready within {timeout}s")

    def _start_isolated(self, ext_path, interpreter):
        """Write the child's temp config and return the argv that starts the runner."""
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

        log.debug("[Bridge] Isolated mode for %s (restrictions: level=%s, network=%s)",
                 self.ext_id, restrictions.get('level'), restrictions.get('network_allowed'))
        if getattr(sys, 'frozen', False):
            try:
                from coreframe.config import DATA_DIR as _dd
                _persist = os.path.join(_dd, 'bin', 'runner', 'CoreFrame.exe')
                if os.path.isfile(_persist):
                    return [_persist, self._config_file]
            except Exception:
                pass
            return [sys.executable, '--ext-runner', self._config_file]
        return [interpreter, runner_path, self._config_file]

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
                    with self._resp_cv:
                        self._read_buffer[rid] = data
                        self._resp_cv.notify_all()
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
            return call_elevated(method, params)

        with self._lock:
            self._rid_seq += 1
            rid = self._rid_seq
        req = _json_dumps({'method': method, 'params': params or {}, 'id': rid}) + '\n'

        with self._lock:
            self._proc.stdin.write(req)
            self._proc.stdin.flush()

# Budgets from measured latency; get_entries (~4s Autoruns scan) is deliberately absent.
        _FAST = ('get_config', 'get_status', 'get_cpu', 'get_ram', 'get_gpu',
                 'get_disk', 'get_fortune', 'get_notes', 'get_ping')
# 4s because get_ip median is 1.46s cold and exceeds 2.0s in 15% of calls.
        _MEDIUM = ('get_ip', 'check_vpn', 'get_open_ports')
        # get_processes needs 6-12 s, 17 s cold: a 4 s budget could never succeed (pitfall 57).
        _SLOW = ('get_processes',)
        # The manifest may declare its own budget: "timeouts": {"get_processes": 20}.
        try:
            declared = self.config.get('timeouts') or {}
        except Exception:
            declared = {}
        if method in declared:
            try:
                timeout = float(declared[method])
            except (TypeError, ValueError):
                timeout = 30
        elif method in _FAST:
            timeout = 2.0
        elif method in _MEDIUM:
            timeout = 4.0
        elif method in _SLOW:
            timeout = 30.0
        else:
            timeout = 30
        deadline = time.monotonic() + timeout
        resp = None
        with self._resp_cv:
            while True:
                resp = self._read_buffer.pop(rid, None)
                if resp is not None:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._resp_cv.wait(remaining)
        if resp is not None:
            if 'error' in resp:
                return {'error': resp['error']}
            result = resp.get('result', resp)
            if isinstance(result, dict):
                return result
            return {'value': result}

        # A strike needs a stale heartbeat: restarting a busy child wipes warm caches (pitfall 26).
        try:
            h = self._ext_isolation.health.get(self.ext_id) if hasattr(self, '_ext_isolation') and self._ext_isolation else None
            if h:
                max_age = getattr(h, 'MAX_HEARTBEAT_AGE', 60.0)
                last_hb = getattr(h, 'last_heartbeat', 0) or 0
                if time.monotonic() - last_hb > max_age:
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
        try:
            with SubprocessBridge._live_lock:
                SubprocessBridge._live_children.discard(self._proc)
        except Exception:
            pass
        # Clean up temp config file
        if self._config_file and os.path.exists(self._config_file):
            try:
                os.remove(self._config_file)
            except OSError:
                pass

    @staticmethod
    def reap_all_children(timeout=8.0):
        """Terminate every tracked child, including orphans. Returns survivors."""
        import time as _t
        with SubprocessBridge._live_lock:
            procs = list(SubprocessBridge._live_children)
        for p in procs:
            try:
                if p.poll() is None:
                    p.terminate()
            except Exception:
                pass
        deadline = _t.monotonic() + timeout
        for p in procs:
            try:
                remaining = deadline - _t.monotonic()
                if remaining <= 0:
                    break
                p.wait(timeout=remaining)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        with SubprocessBridge._live_lock:
            SubprocessBridge._live_children = {p for p in SubprocessBridge._live_children if p.poll() is None}
            return len(SubprocessBridge._live_children)

    def heartbeat(self):
        try:
            return self._call('heartbeat', {})
        except Exception:
            return {'error': 'Heartbeat failed'}
