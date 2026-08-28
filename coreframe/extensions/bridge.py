import os
import sys
import json
import time
import threading
import subprocess as _subprocess

from coreframe.config import log

# Force no console windows on any subprocess
if sys.platform.startswith('win'):
    import ctypes
    _CREATE_NO_WINDOW = 0x08000000
    _DETACHED_PROCESS = 0x00000008
    _orig_init = _subprocess.Popen.__init__
    def _patched_init(self, *args, **kwargs):
        old = kwargs.get('creationflags', 0)
        newflags = old | _CREATE_NO_WINDOW | _DETACHED_PROCESS
        kwargs['creationflags'] = newflags
        return _orig_init(self, *args, **kwargs)
    _subprocess.Popen.__init__ = _patched_init
subprocess = _subprocess


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
        self._proc = None
        self._lock = threading.Lock()
        self._reader_lock = threading.Lock()
        self._read_buffer = {}
        self._running = True
        self._started = False
        self._start_time = 0.0
        self._ext_isolation = ext_isolation
        self._start(ext_path)

    def _start(self, ext_path):
        main_path = os.path.join(ext_path, self.main)
        if not os.path.isfile(main_path):
            raise FileNotFoundError(f"Main file not found: {main_path}")

        interpreter = self._LANG_MAP.get(self.language)
        if not interpreter:
            raise RuntimeError(f"Unsupported language: {self.language}")

        cmd = [interpreter, main_path]

        startupinfo = None
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

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

        # Start heartbeat sender for subprocess extensions
        if self.language not in ('python', 'py'):
            self._hb_thread = threading.Thread(target=self._heartbeat_sender, daemon=True, name=f'bridge-hb-{self.ext_id}')
            self._hb_thread.start()

    def _heartbeat_sender(self):
        while self._running and self._proc and self._proc.poll() is None:
            time.sleep(10.0)
            if not self._running or not self._proc or self._proc.poll() is not None:
                break
            try:
                with self._lock:
                    self._proc.stdin.write(json.dumps({'method': 'heartbeat'}) + '\n')
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
                data = json.loads(line)
                if data.get('method') == 'heartbeat':
                    self._ext_isolation.heartbeat(self.ext_id)
                    continue
                rid = data.get('id')
                if rid is not None:
                    with self._reader_lock:
                        self._read_buffer[rid] = data
            except (json.JSONDecodeError, ValueError, OSError):
                pass
        err = self._proc.stderr.read() if self._proc and self._proc.poll() is not None else ''
        if err:
            log.warning("[Bridge] %s stderr: %s", self.ext_id, err.strip())

    def _call(self, method, params=None):
        if not self._proc or self._proc.poll() is not None:
            raise RuntimeError(f"Extension {self.ext_id} process is dead")

        rid = int(time.time() * 1000) % 1000000 + id(method) % 1000
        req = json.dumps({'method': method, 'params': params or {}, 'id': rid}) + '\n'

        with self._lock:
            self._proc.stdin.write(req)
            self._proc.stdin.flush()

        deadline = time.time() + 30
        while time.time() < deadline:
            with self._reader_lock:
                resp = self._read_buffer.pop(rid, None)
            if resp is not None:
                if 'error' in resp:
                    return {'error': resp['error']}
                return {'value': resp.get('result', resp)}
            time.sleep(0.01)

        return {'error': 'Timeout: extension did not respond in 30s'}

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

    def heartbeat(self):
        try:
            return self._call('heartbeat', {})
        except Exception:
            return {'error': 'Heartbeat failed'}
