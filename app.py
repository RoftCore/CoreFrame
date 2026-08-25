import io
import os
import json
import hashlib
import logging
import importlib.util
import importlib.metadata
import re
import signal
import shutil
import subprocess as _subprocess
import sys
import threading
import time
import urllib.request
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable
import threading

#  Force no console windows on any subprocess 
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
subprocess = _subprocess  # alias
import zipfile
from flask import Flask, Response, jsonify, request, send_from_directory, send_file
from flask_socketio import SocketIO, emit

# Force bundle eventlet for PyInstaller (needed by flask-socketio)
try:
    import eventlet
except ImportError:
    pass


#  Extension Health & Isolation 

@dataclass
class ExtensionHealth:
    ext_id: str
    status: str = 'loading'  # loading, healthy, degraded, dead
    load_time: float = 0.0
    last_heartbeat: float = 0.0
    error_count: int = 0
    last_error: str = ''
    restart_count: int = 0
    load_thread: Optional[threading.Thread] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


class ExtensionIsolation:
    """Per-extension isolation with timeout, health monitoring, and auto-recovery."""
    
    MAX_LOAD_TIME = 10.0  # seconds
    MAX_HEARTBEAT_AGE = 30.0  # seconds
    MAX_RESTARTS = 3
    RESTART_COOLDOWN = 5.0  # seconds
    
    def __init__(self):
        self.health: Dict[str, ExtensionHealth] = {}
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='ext-load')
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
    
    def start_monitor(self):
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_monitor.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name='ext-health-monitor')
            self._monitor_thread.start()
    
    def stop_monitor(self):
        self._stop_monitor.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        self._executor.shutdown(wait=False, cancel_futures=True)
    
    def _monitor_loop(self):
        while not self._stop_monitor.is_set():
            time.sleep(2.0)
            self._check_health()
    
    def _check_health(self):
        now = time.monotonic()
        with self._lock:
            for ext_id, health in list(self.health.items()):
                if health.status == 'dead':
                    continue
                # Check heartbeat for running extensions
                if health.status == 'healthy' and health.last_heartbeat > 0:
                    if now - health.last_heartbeat > self.MAX_HEARTBEAT_AGE:
                        log.warning("Extension %s heartbeat timeout, marking degraded", ext_id)
                        health.status = 'degraded'
                # Auto-restart degraded extensions
                if health.status == 'degraded' and health.restart_count < self.MAX_RESTARTS:
                    if now - health.last_heartbeat > self.RESTART_COOLDOWN:
                        log.info("Auto-restarting degraded extension %s (attempt %d/%d)", 
                                ext_id, health.restart_count + 1, self.MAX_RESTARTS)
                        self._schedule_restart(ext_id)
    
    def _schedule_restart(self, ext_id: str):
        health = self.health.get(ext_id)
        if not health:
            return
        health.cancel_event.set()
        health.restart_count += 1
        health.status = 'loading'
        health.load_time = 0.0
        health.cancel_event = threading.Event()
        # Trigger reload via socketio (will be handled by frontend)
        socketio.emit('extension_restart', {'id': ext_id, 'attempt': health.restart_count})
    
    def start_load(self, ext_id: str, loader_fn: Callable[[], bool]) -> threading.Thread:
        health = ExtensionHealth(ext_id=ext_id)
        with self._lock:
            self.health[ext_id] = health
        
        def wrapped_loader():
            start = time.monotonic()
            health.load_time = 0.0
            try:
                future = self._executor.submit(loader_fn)
                try:
                    result = future.result(timeout=self.MAX_LOAD_TIME)
                    health.load_time = time.monotonic() - start
                    if result and not health.cancel_event.is_set():
                        health.status = 'healthy'
                        health.last_heartbeat = time.monotonic()
                        log.info("Extension %s loaded in %.2fs", ext_id, health.load_time)
                    else:
                        health.status = 'dead'
                        health.last_error = 'Load cancelled or returned False'
                except FuturesTimeoutError:
                    health.status = 'dead'
                    health.last_error = f'Load timeout ({self.MAX_LOAD_TIME}s)'
                    log.error("Extension %s load timeout after %.1fs", ext_id, self.MAX_LOAD_TIME)
                    future.cancel()
                except Exception as e:
                    health.status = 'dead'
                    health.last_error = str(e)
                    health.error_count += 1
                    log.error("Extension %s load failed: %s", ext_id, e)
            finally:
                health.load_thread = None
        
        thread = threading.Thread(target=wrapped_loader, daemon=True, name=f'ext-load-{ext_id}')
        health.load_thread = thread
        thread.start()
        return thread
    
    def heartbeat(self, ext_id: str):
        with self._lock:
            health = self.health.get(ext_id)
            if health and health.status in ('healthy', 'degraded'):
                health.last_heartbeat = time.monotonic()
                if health.status == 'degraded':
                    health.status = 'healthy'
    
    def mark_dead(self, ext_id: str, error: str = ''):
        with self._lock:
            health = self.health.get(ext_id)
            if health:
                health.status = 'dead'
                health.last_error = error
                health.cancel_event.set()
    
    def get_status(self, ext_id: str) -> dict:
        with self._lock:
            health = self.health.get(ext_id)
            if not health:
                return {'status': 'unknown'}
            return {
                'status': health.status,
                'load_time': health.load_time,
                'error_count': health.error_count,
                'last_error': health.last_error,
                'restart_count': health.restart_count,
            }
    
    def get_all_status(self) -> dict:
        with self._lock:
            return {ext_id: self.get_status(ext_id) for ext_id in self.health}


# Global isolation manager
_ext_isolation = ExtensionIsolation()

def _patch_pip_for_frozen():
    """distlib.resources.finder() only knows standard loaders (SourceFileLoader,
    FileFinder, zipimporter). Under PyInstaller the modules for pip._vendor.distlib
    are loaded by a frozen importer, so finder() raises
    "Unable to locate finder for 'pip._vendor.distlib'". We instead register the
    frozen loader and point ResourceFinder at the extracted package dir in
    _MEIPASS (collect_all('pip') ships those files as data)."""
    if not getattr(sys, 'frozen', False):
        return
    try:
        from pip._vendor.distlib import resources as _dr
    except Exception:
        return
    try:
        import pip._vendor.distlib as _distlib
    except Exception:
        return
    loader = getattr(_distlib, '__loader__', None)
    if loader is None:
        return
    loader_type = type(loader)
    if loader_type in _dr._finder_registry:
        return
    import types
    meipass = getattr(sys, '_MEIPASS', None)
    base = os.path.dirname(os.path.abspath(getattr(_distlib, '__file__', '')))
    if meipass:
        candidate = os.path.join(meipass, 'pip', '_vendor', 'distlib')
        if os.path.isdir(candidate):
            base = candidate

    def _make_finder(module):
        fake = types.ModuleType('pip._vendor.distlib')
        fake.__file__ = os.path.join(base, '__init__.py')
        if os.path.exists(os.path.join(base, '__init__.py')):
            return _dr.ResourceFinder(fake)
        return _dr.ResourceFinder(module)

    _dr._finder_registry[loader_type] = _make_finder
    _dr._finder_cache.clear()
    log.debug("Registered distlib resource finder for frozen loader %s", loader_type)


def _find_distribution(name):
    """Return (canonical name, version) for an installed distribution, if any,
    trying a few name spellings (case/normalization mismatches like
    `SpotipyFree` vs `spotipyfree`)."""
    candidates = {name, name.replace('-', '_'), name.replace('_', '-')}
    for cand in candidates:
        try:
            dist = importlib.metadata.distribution(cand)
            return (dist.metadata.get('Name', cand), dist.version)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None

def _version_satisfies(spec_str, version, name):
    """Check installed `version` against a PEP 440 spec (e.g. '>=2.1.5,<3')."""
    if not spec_str:
        return True
    try:
        from pip._vendor.packaging.specifiers import SpecifierSet
    except Exception:
        return True  # can't be sure: keep it, pip will resolve
    return SpecifierSet(spec_str).contains(version, prereleases=True)


def _ensure_extension_deps(ext_path):
    req_path = os.path.join(ext_path, 'requirements.txt')
    if not os.path.exists(req_path):
        return
    missing = []
    with open(req_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Allowed: "flask", "yt-dlp>=2023.7.6", "spotifyscraper>=2.1.5,<3"
            head = re.split(r'[<>=~!]', line)[0].strip()
            name = re.sub(r'\[.*\]$', '', head).strip()
            if not name:
                continue
            spec_str = line[len(head):].strip()
            mod_name = name.lower().replace('-', '_').replace('.', '_')
            found_dist = _find_distribution(name)
            found_mod = importlib.util.find_spec(mod_name) is not None

            installed_ok = False
            if found_dist:
                installed_ok = _version_satisfies(spec_str, found_dist[1], name)
            elif not spec_str and found_mod:
                # No version pin and the module import works (e.g. bundled copy).
                installed_ok = True
            if installed_ok:
                continue
            # Requirement is missing OR the installed version fails the pin:
            # pass the full spec line to pip so it installs the right version.
            missing.append(line)
    if not missing:
        return
    log.info("Installing missing deps: %s", missing)
    _patch_pip_for_frozen()
    try:
        from pip._internal.cli.main import main as _pip_main
        _pip_main(['install', '--target', SHARED_LIB_DIR, '--no-input', '--quiet'] + missing)
    except Exception as e:
        log.warning("Failed to install deps: %s", e)

#  Paths 

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if sys.platform.startswith('win'):
    _CSIDL_PERSONAL = 0x0005
    _SHGFP_TYPE_CURRENT = 0
    _buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, _CSIDL_PERSONAL, None, _SHGFP_TYPE_CURRENT, _buf)
    DATA_DIR = os.path.join(_buf.value, 'CoreFrame')
else:
    DATA_DIR = os.path.join(os.path.expanduser('~'), '.local', 'share', 'CoreFrame')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
EXTENSIONS_DIR = os.path.join(DATA_DIR, 'extensions')
REGISTRY_PATH = os.path.join(DATA_DIR, 'extensions.json')
WIDGET_STATE_PATH = os.path.join(DATA_DIR, 'widget_state.json')
_widget_state_lock = threading.Lock()
SHARED_LIB_DIR = os.path.join(DATA_DIR, 'lib')

DATA_DATA_DIR = os.path.join(DATA_DIR, 'data')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXTENSIONS_DIR, exist_ok=True)
os.makedirs(SHARED_LIB_DIR, exist_ok=True)
os.makedirs(DATA_DATA_DIR, exist_ok=True)

MARKETPLACE_URL = 'https://raw.githubusercontent.com/RoftCore/extensions-coreframe/main/registry.json'
if SHARED_LIB_DIR not in sys.path:
    # Keep bundled deps (MEIPASS) ahead of SHARED_LIB_DIR: extensions pip-install
    # deps into lib/ that can shadow the frozen copies (e.g. stale cffi -> version
    # mismatch with the compiled _cffi_backend in the bundle).
    if getattr(sys, 'frozen', False) and sys.path and sys.path[0] == getattr(sys, '_MEIPASS', None):
        sys.path.insert(1, SHARED_LIB_DIR)
    else:
        sys.path.insert(0, SHARED_LIB_DIR)

LOG_PATH = os.path.join(DATA_DIR, 'coreframe.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
    ]
)
log = logging.getLogger('CoreFrame')

#  Extract bundled extensions (embedded .exe) 
_bundled_ext_dir = os.path.join(BASE_DIR, 'extensions')
if getattr(sys, 'frozen', False) and os.path.isdir(_bundled_ext_dir):
    for _name in os.listdir(_bundled_ext_dir):
        _src = os.path.join(_bundled_ext_dir, _name)
        _dst = os.path.join(EXTENSIONS_DIR, _name)
        if os.path.isdir(_src) and not os.path.exists(_dst):
            shutil.copytree(_src, _dst, ignore_dangling_symlinks=True)
            log.info("Extracted bundled extension: %s", _name)

#  Flask 

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = hashlib.sha256(os.urandom(32)).hexdigest()
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=["http://127.0.0.1:8420", "http://localhost:8420"])

_LOCAL_TOKEN = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
extensions = {}
failed_extensions = {}
latest_update = {}
_client_count = 0
_shutdown_callback = None  # Set by run_coreframe.pyw to close window gracefully

#  Extension loading 

def _sync_extension_lib(ext_path):
    ext_lib = os.path.join(ext_path, 'lib')
    if os.path.isdir(ext_lib):
        for item in os.listdir(ext_lib):
            src = os.path.join(ext_lib, item)
            dst = os.path.join(SHARED_LIB_DIR, item)
            if not os.path.exists(dst):
                if os.path.isdir(src):
                    shutil.copytree(src, dst, ignore_dangling_symlinks=True)
                else:
                    shutil.copy2(src, dst)
                log.debug("Synced %s to shared lib", item)
        # Remove the shipped lib/ after sync — no duplicates
        try:
            shutil.rmtree(ext_lib)
            log.debug("Removed shipped lib/ from %s", ext_path)
        except Exception:
            pass


def _load_extension_core(ext_id: str, ext_path: str) -> tuple[bool, str]:
    """Core loading logic - returns (success, error_msg). No side effects on failure."""
    config_path = os.path.join(ext_path, 'extension.json')
    main_path = os.path.join(ext_path, 'main.py')
    
    if not os.path.exists(config_path):
        return False, "No extension.json"
    if not os.path.exists(main_path):
        return False, "No main.py"
    
    try:
        with open(config_path, encoding='utf-8-sig') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"Invalid extension.json: {e}"
    except Exception as e:
        return False, f"Config read error: {e}"
    
    current_os = 'linux' if not sys.platform.startswith('win') else 'windows'
    platforms = config.get('platforms')
    if platforms is not None and current_os not in platforms:
        return False, f"Platform mismatch: {current_os} not in {platforms}"
    
    try:
        _sync_extension_lib(ext_path)
        _ensure_extension_deps(ext_path)
        config['data_dir'] = os.path.join(DATA_DATA_DIR, ext_id)
        lang = config.get('language', 'python')
        
        if lang != 'python' and lang != 'py':
            ext_instance = SubprocessBridge(config, ext_path)
        else:
            mod_name = f"extensions.{ext_id}"
            # Clean any stale module
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            spec = importlib.util.spec_from_file_location(mod_name, main_path)
            if spec is None or spec.loader is None:
                return False, "Failed to create module spec"
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            
            # Verify Extension class exists
            if not hasattr(module, 'Extension'):
                return False, "Module has no Extension class"
            
            ext_instance = module.Extension(config)
        
        # Verify instance has required methods
        if not hasattr(ext_instance, 'on_stop'):
            log.warning("Extension %s missing on_stop method", ext_id)
        
        # Atomic swap into extensions dict
        extensions[ext_id] = {'config': config, 'instance': ext_instance}
        failed_extensions.pop(ext_id, None)
        
        # Start polling if realtime
        _start_polling(ext_id, extensions[ext_id])
        
        return True, ""
    except Exception as e:
        # Clean up on failure
        mod_name = f"extensions.{ext_id}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        extensions.pop(ext_id, None)
        return False, str(e)


def load_extensions():
    """NON-BLOCKING: Starts async loading of all extensions. Returns immediately."""
    log.info("load_extensions: Starting async load (EXTENSIONS_DIR=%s)", EXTENSIONS_DIR)
    _ext_isolation.start_monitor()
    
    if not os.path.exists(EXTENSIONS_DIR):
        log.info("Extensions dir does not exist: %s", EXTENSIONS_DIR)
        return
    
    # Quick scan - just collect valid extension dirs
    candidates = []
    for name in os.listdir(EXTENSIONS_DIR):
        ext_path = os.path.join(EXTENSIONS_DIR, name)
        if not os.path.isdir(ext_path):
            continue
        config_path = os.path.join(ext_path, 'extension.json')
        main_path = os.path.join(ext_path, 'main.py')
        if os.path.exists(config_path) and os.path.exists(main_path):
            candidates.append((name, ext_path))
    
    log.info("Found %d candidate extensions", len(candidates))
    
    # Fire off all loads in parallel with isolation
    for ext_id, ext_path in candidates:
        def make_loader(eid, epath):
            def loader():
                success, error = _load_extension_core(eid, epath)
                if not success:
                    failed_extensions[eid] = {'name': eid, 'loadError': error}
                    _ext_isolation.mark_dead(eid, error)
                    log.error("Extension %s failed: %s", eid, error)
                return success
            return loader
        
        _ext_isolation.start_load(ext_id, make_loader(ext_id, ext_path))


def _load_single_extension(ext_id):
    """Blocking load for dynamic installs - uses isolation with timeout."""
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    config_path = os.path.join(ext_path, 'extension.json')
    if not os.path.exists(config_path):
        return False
    
    def loader():
        success, error = _load_extension_core(ext_id, ext_path)
        if not success:
            failed_extensions[ext_id] = {'name': ext_id, 'loadError': error}
            _ext_isolation.mark_dead(ext_id, error)
        return success
    
    thread = _ext_isolation.start_load(ext_id, loader)
    thread.join(timeout=15.0)  # Wait for dynamic install
    return ext_id in extensions

#  Multi-language bridge 

class SubprocessBridge:
    _LANG_MAP = {
        'node': 'node',
        'nodejs': 'node',
        'javascript': 'node',
        'python': sys.executable,
        'py': sys.executable,
    }

    def __init__(self, config, ext_path):
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
        self._start(ext_path)

    def _start(self, ext_path):
        main_path = os.path.join(ext_path, self.main)
        if not os.path.isfile(main_path):
            raise FileNotFoundError(f"Main file not found: {main_path}")

        interpreter = self._LANG_MAP.get(self.language)
        if not interpreter:
            raise RuntimeError(f"Unsupported language: {self.language}")

        if self.language in ('python', 'py'):
            cmd = [interpreter, main_path]
        else:
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
        """Send periodic heartbeats to subprocess extension."""
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
                # Heartbeat for health monitoring
                if data.get('method') == 'heartbeat':
                    _ext_isolation.heartbeat(self.ext_id)
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
        """Send heartbeat to subprocess to confirm it's alive."""
        try:
            return self._call('heartbeat', {})
        except Exception:
            return {'error': 'Heartbeat failed'}

#  Auth 

@app.route('/api/token')
def api_token():
    return jsonify({'token': _LOCAL_TOKEN})

@app.route('/api/debug')
def api_debug():
    try:
        ext_dir_contents = os.listdir(EXTENSIONS_DIR) if os.path.isdir(EXTENSIONS_DIR) else []
    except Exception:
        ext_dir_contents = []
    return jsonify({
        'debug': app.debug,
        'data_dir': DATA_DIR,
        'extensions_dir': EXTENSIONS_DIR,
        'extensions_dir_exists': os.path.isdir(EXTENSIONS_DIR),
        'extensions_in_dir': ext_dir_contents,
        'base_dir': BASE_DIR,
        'frozen': getattr(sys, 'frozen', False),
        'cwd': os.getcwd(),
        'loaded_extensions': list(extensions.keys()),
    })

#  Autostart 

AUTOSTART_KEY = 'CoreFrame'

def _get_autostart_enabled():
    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
            try:
                val, _ = winreg.QueryValueEx(key, AUTOSTART_KEY)
                winreg.CloseKey(key)
                return os.path.isfile(val)
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        elif sys.platform == 'linux':
            path = os.path.join(os.path.expanduser('~'), '.config', 'autostart', 'coreframe.desktop')
            return os.path.isfile(path)
        return False
    except Exception:
        return False

def _set_autostart_enabled(enable):
    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE)
            if enable:
                # Use --autostart flag to start hidden/minimized on boot
                winreg.SetValueEx(key, AUTOSTART_KEY, 0, winreg.REG_SZ, f'"{sys.executable}" --autostart')
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_KEY)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        elif sys.platform == 'linux':
            autostart_dir = os.path.join(os.path.expanduser('~'), '.config', 'autostart')
            path = os.path.join(autostart_dir, 'coreframe.desktop')
            if enable:
                os.makedirs(autostart_dir, exist_ok=True)
                content = (
                    '[Desktop Entry]\n'
                    'Type=Application\n'
                    'Name=CoreFrame\n'
                    f'Exec={sys.executable} --autostart\n'
                    'Terminal=false\n'
                )
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                if os.path.isfile(path):
                    os.remove(path)
            return True
        return False
    except Exception:
        return False

@app.route('/api/autostart', methods=['GET', 'POST'])
def api_autostart():
    frozen = getattr(sys, 'frozen', False)
    if request.method == 'POST':
        if not frozen:
            return jsonify({'error': 'Not available', 'available': False, 'enabled': False}), 400
        enabled = _get_autostart_enabled()
        _set_autostart_enabled(not enabled)
    return jsonify({
        'enabled': _get_autostart_enabled(),
        'available': frozen
    })

@app.before_request
def check_token():
    if request.path.startswith('/api/') and request.path not in ('/api/token', '/api/health', '/api/debug', '/api/debug.js'):
        if request.path.startswith('/api/package_extension/') or request.path.startswith('/api/scenes/image/'):
            return
        token = request.headers.get('X-CoreFrame-Token', '')
        if token != _LOCAL_TOKEN:
            return jsonify({'error': 'Unauthorized'}), 403

#  Extension info 

@app.route('/api/extensions')
def api_extensions():
    result = {}
    for ext_id, ext_data in extensions.items():
        cfg = ext_data['config']
        result[ext_id] = {
            'id': ext_id,
            'name': cfg.get('name', ext_id),
            'icon': cfg.get('icon', ''),
            'category': cfg.get('category', 'general'),
            'menu_items': cfg.get('menu_items', []),
            'widgets': cfg.get('widgets', []),
            'grid_size': cfg.get('grid_size'),
            'overlayable': cfg.get('overlayable', False),
            'realtime': cfg.get('realtime', False),
            'refresh_interval': cfg.get('refresh_interval', 5000),
            'platforms': cfg.get('platforms'),
            'js_modules': cfg.get('js_modules', []),
            'css_modules': cfg.get('css_modules', []),
            'author': cfg.get('author', ''),
            'version': cfg.get('version', '1.0'),
            'language': cfg.get('language', 'python'),
            'main': cfg.get('main', 'main.py'),
            'scroll': cfg.get('scroll'),
            'hideScrollbar': cfg.get('hideScrollbar', False)
        }
    for ext_id, ext_data in failed_extensions.items():
        result[ext_id] = {
            'id': ext_id,
            'name': ext_data.get('name', ext_id),
            'loadError': ext_data.get('loadError', 'Unknown error'),
            'widgets': []
        }
    return jsonify(result)

@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'ok',
        'extensions': len(extensions),
        'clients': _client_count,
    })


@app.route('/api/extensions/health')
def api_extensions_health():
    """Get health status of all extensions."""
    health_data = _ext_isolation.get_all_status()
    result = {}
    for ext_id, health in health_data.items():
        ext_info = extensions.get(ext_id, {}).get('config', {})
        failed_info = failed_extensions.get(ext_id, {})
        result[ext_id] = {
            'id': ext_id,
            'name': ext_info.get('name', ext_id) or failed_info.get('name', ext_id),
            'status': health['status'],
            'load_time': health.get('load_time', 0),
            'error_count': health.get('error_count', 0),
            'last_error': health.get('last_error', ''),
            'restart_count': health.get('restart_count', 0),
            'loaded': ext_id in extensions,
            'load_error': failed_info.get('loadError'),
        }
    return jsonify(result)


@app.route('/api/extension/<ext_id>/heartbeat', methods=['POST'])
def api_extension_heartbeat(ext_id):
    """Receive heartbeat from extension."""
    if ext_id not in extensions:
        return jsonify({'error': 'Extension not loaded'}), 404
    _ext_isolation.heartbeat(ext_id)
    return jsonify({'ok': True})


@app.route('/api/window/focus', methods=['POST'])
def api_window_focus():
    """Focus the main window - called by second instance trying to start."""
    socketio.emit('focus_window')
    return jsonify({'ok': True})

@app.route('/api/extension/<ext_id>/<action>', methods=['GET', 'POST'])
def api_extension_action(ext_id, action):
    if ext_id not in extensions:
        return jsonify({'error': 'Extension not found'}), 404
    try:
        ext = extensions[ext_id]['instance']
        method = getattr(ext, action, None)
        if not method:
            return jsonify({'error': f'Action {action} not found'}), 404
        if request.method == 'POST':
            result = method(request.get_json(silent=True) or {})
        else:
            result = method()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ext-static/<ext_id>/<path:path>')
def ext_static(ext_id, path):
    ext_dir = os.path.join(EXTENSIONS_DIR, ext_id)
    static_dir = os.path.join(ext_dir, 'static')
    if not os.path.isdir(static_dir):
        return Response('', 204)
    try:
        return send_from_directory(static_dir, path)
    except FileNotFoundError:
        return Response('', 204)

#  Install extension 

@app.route('/api/install_extension', methods=['POST'])
def api_install_extension():
    if 'extension' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['extension']
    if not f.filename.endswith('.zip'):
        return jsonify({'error': 'File must be a .zip'}), 400
    try:
        zf = zipfile.ZipFile(io.BytesIO(f.read()))
        names = zf.namelist()
        has_subdir = any(n.count('/') >= 1 and n.split('/')[-1] == 'extension.json' for n in names)
        ext_config = None
        ext_main = None
        for n in names:
            base = n.split('/')[-1]
            if base == 'extension.json':
                ext_config = n
            elif base == 'main.py':
                ext_main = n
        if not ext_config or not ext_main:
            return jsonify({'error': 'Extension must contain extension.json and main.py'}), 400
        cfg_data = json.loads(zf.read(ext_config))
        ext_id = cfg_data.get('id')
        if not ext_id:
            parts = ext_config.split('/')
            ext_id = parts[0] if len(parts) >= 2 else f.filename.replace('.zip', '')
        ext_name = cfg_data.get('name', ext_id)
        target = os.path.join(EXTENSIONS_DIR, ext_id)
        existing_cfg = os.path.join(target, 'extension.json')
        if os.path.exists(existing_cfg):
            try:
                with open(existing_cfg, encoding='utf-8-sig') as _f:
                    _existing = json.load(_f)
                if _existing.get('id') == ext_id:
                    return jsonify({'exists': True, 'message': f'Extension "{ext_name}" has already been imported before and cannot be imported again.'})
            except Exception:
                pass
            # Corrupted or mismatched — delete and reinstall
            shutil.rmtree(target, ignore_errors=True)
        elif os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
        static_assets_install = set(cfg_data.get('js_modules', []) + cfg_data.get('css_modules', []))
        prefix = ''
        if has_subdir and ext_config.count('/') >= 1:
            prefix = ext_config.rsplit('/', 1)[0] + '/'
        os.makedirs(target, exist_ok=True)
        for n in names:
            if n.endswith('/'):
                continue
            if prefix and n.startswith(prefix):
                rel = n[len(prefix):]
            elif has_subdir:
                parts = n.split('/')
                rel = '/'.join(parts[1:]) if len(parts) >= 2 else parts[-1]
            else:
                rel = n
            if not rel:
                continue
            # Wrap static assets in static/ for correct server serving
            if rel in static_assets_install and not rel.startswith('static/'):
                rel = os.path.join('static', rel)
            dest = os.path.join(target, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as out:
                out.write(zf.read(n))
        zf.close()
        # Update registry
        try:
            with open(REGISTRY_PATH, encoding='utf-8') as rf:
                registry = json.load(rf)
        except (FileNotFoundError, json.JSONDecodeError):
            registry = {}
        registry[ext_id] = {
            'name': ext_name,
            'version': cfg_data.get('version', '1.0'),
            'author': cfg_data.get('author', ''),
            'category': cfg_data.get('category', 'general'),
        }
        with open(REGISTRY_PATH, 'w', encoding='utf-8') as rf:
            json.dump(registry, rf, indent=2)

        # Load in background — pip deps are slow, don't block the UI
        def _bg_install(ext_id, ext_path):
            try:
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'syncing'})
                _sync_extension_lib(ext_path)
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'deps'})
                _ensure_extension_deps(ext_path)
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'loading'})
                if _load_single_extension(ext_id):
                    ext_data = extensions.get(ext_id)
                    if ext_data:
                        _start_polling(ext_id, ext_data)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'done'})
                else:
                    err_msg = failed_extensions.get(ext_id, {}).get('loadError', 'Unknown error')
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': err_msg})
            except Exception as e:
                log.error("Background install failed for %s: %s", ext_id, e)
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': str(e)})

        t = threading.Thread(target=_bg_install, args=(ext_id, target), daemon=True)
        t.start()
        return jsonify({'status': 'installing', 'id': ext_id, 'name': ext_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extensions/<ext_id>', methods=['DELETE'])
def api_delete_extension(ext_id):
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    if not os.path.isdir(ext_path):
        return jsonify({'error': 'Extension not found'}), 404

    # Cleanup extension before deleting
    ext_data = extensions.get(ext_id)
    if ext_data:
        inst = ext_data.get('instance')
        cleanup = getattr(inst, 'cleanup', None)
        if cleanup:
            try:
                cleanup()
            except Exception as e:
                log.warning("Cleanup failed for %s: %s", ext_id, e)

    # Retry rmtree with backoff in case cleanup releases handles asynchronously
    last_err = None
    for attempt in range(5):
        try:
            shutil.rmtree(ext_path)
            break
        except Exception as e:
            last_err = str(e)
            if attempt < 4:
                time.sleep(0.5)
            else:
                return jsonify({'error': f'Failed to delete extension files: {last_err}'}), 500

    # Unload from memory
    extensions.pop(ext_id, None)
    failed_extensions.pop(ext_id, None)
    mod_name = f"extensions.{ext_id}"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    # Remove widgets of this extension from all scenes
    try:
        state = load_widget_state()
        scenes = state.get('scenes')
        if scenes:
            changed = False
            for sid, scene in scenes.items():
                if isinstance(scene, dict) and ext_id in scene.get('widgets', {}):
                    del scene['widgets'][ext_id]
                    changed = True
            if changed:
                state['scenes'] = scenes
                save_widget_state(state)
                log.info("Cleaned up %s widgets from all scenes", ext_id)
    except Exception as e:
        log.warning("Failed to clean up widgets for %s: %s", ext_id, e)

    # Remove from registry
    try:
        with open(REGISTRY_PATH, encoding='utf-8') as rf:
            registry = json.load(rf)
        registry.pop(ext_id, None)
        with open(REGISTRY_PATH, 'w', encoding='utf-8') as rf:
            json.dump(registry, rf, indent=2)
    except Exception:
        pass

    log.info("Extension deleted: %s", ext_id)
    return jsonify({'ok': True, 'id': ext_id})

#  Static frontend 

@app.route('/api/debug.js')
def api_debug_js():
    frozen = getattr(sys, 'frozen', False)
    debug_status = 'false' if frozen else 'true'
    return Response(f'const _COREFRAME_DEBUG = {debug_status};', mimetype='application/javascript')

@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(STATIC_DIR, path)

#  Package extension 

@app.route('/api/package_extension/<ext_id>')
def api_package_extension(ext_id):
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    if not os.path.isdir(ext_path):
        return jsonify({'error': 'Extension not found'}), 404

    author = request.args.get('author', '').strip()

    # Load current extension.json to merge author
    config_path = os.path.join(ext_path, 'extension.json')
    config = {}
    try:
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)
    except Exception:
        pass

    # Build the zip in memory
    try:
        buf = io.BytesIO()
        static_assets = set(config.get('js_modules', []) + config.get('css_modules', []))
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(ext_path):
                dirs[:] = [d for d in dirs if d not in ('__pycache__', 'Downloads_playlists') and not d.startswith('.')]
                for f in files:
                    if f.endswith(('.pyc', '.pyo', '.zip', '.mp3', '.webp', '.jpg', '.jpeg', '.png')):
                        continue
                    if f in ('config.json',):
                        continue
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, ext_path)
                    # Wrap static assets in static/ subdirectory for correct serving
                    if rel in static_assets and not rel.startswith('static/'):
                        rel = os.path.join('static', rel)
                    zf.write(full, rel)

            # Inject / update author in extension.json
            if author:
                config['author'] = author
            zf.writestr('extension.json', json.dumps(config, indent=2))

            # Extension itself (lib/ included via os.walk if present)

        buf.seek(0)
        return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{ext_id}.zip')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#  Marketplace 

MARKETPLACE_CACHE = None
MARKETPLACE_CACHE_TIME = 0

@app.route('/api/marketplace/list')
def api_marketplace_list():
    global MARKETPLACE_CACHE, MARKETPLACE_CACHE_TIME
    now = time.time()
    if MARKETPLACE_CACHE and now - MARKETPLACE_CACHE_TIME < 120:
        return jsonify(MARKETPLACE_CACHE)
    try:
        req = urllib.request.Request(MARKETPLACE_URL)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        MARKETPLACE_CACHE = data
        MARKETPLACE_CACHE_TIME = now
        return jsonify(data)
    except Exception as e:
        log.error("Marketplace fetch failed: %s", e)
        return jsonify({'error': str(e)}), 502

@app.route('/api/marketplace/install/<ext_id>', methods=['POST'])
def api_marketplace_install(ext_id):
    # First fetch registry to get the download_url
    try:
        req = urllib.request.Request(MARKETPLACE_URL)
        with urllib.request.urlopen(req, timeout=10) as r:
            registry = json.loads(r.read())
    except Exception as e:
        return jsonify({'error': f'Failed to fetch registry: {e}'}), 502

    ext_info = None
    for ex in registry.get('extensions', []):
        if ex['id'] == ext_id:
            ext_info = ex
            break
    if not ext_info:
        return jsonify({'error': f'Extension "{ext_id}" not found in marketplace'}), 404

    target = os.path.join(EXTENSIONS_DIR, ext_id)
    existing_cfg = os.path.join(target, 'extension.json')
    if os.path.exists(existing_cfg):
        try:
            with open(existing_cfg, encoding='utf-8-sig') as _f:
                _existing = json.load(_f)
            if _existing.get('id') == ext_id:
                return jsonify({'exists': True, 'message': f'Extension "{ext_info.get("name", ext_id)}" has already been imported before and cannot be imported again.'})
        except Exception:
            pass
        shutil.rmtree(target, ignore_errors=True)
    elif os.path.exists(target):
        shutil.rmtree(target, ignore_errors=True)

    url = ext_info.get('download_url')
    if not url:
        return jsonify({'error': 'No download URL for this extension'}), 404

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:
        return jsonify({'error': f'Download failed: {e}'}), 502

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        prefix = ''
        for n in names:
            if n.endswith('/'):
                continue
            parts = n.split('/')
            if len(parts) >= 2:
                prefix = parts[0] + '/'
                break
        mi_config = None
        mi_ext_config_path = None
        for n in names:
            base = n.split('/')[-1]
            if base == 'extension.json':
                mi_ext_config_path = n
                break
        if mi_ext_config_path:
            mi_config = json.loads(zf.read(mi_ext_config_path))
        mi_static_assets = set(mi_config.get('js_modules', []) + mi_config.get('css_modules', [])) if mi_config else set()
        os.makedirs(target, exist_ok=True)
        for n in names:
            if n.endswith('/'):
                continue
            rel = n[len(prefix):] if prefix and n.startswith(prefix) else n
            if rel in mi_static_assets and not rel.startswith('static/'):
                rel = os.path.join('static', rel)
            dest = os.path.join(target, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as out:
                out.write(zf.read(n))
        zf.close()
        # Load in background
        def _bg_install_mkt(ext_id, target, ext_name):
            try:
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'syncing'})
                _sync_extension_lib(target)
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'deps'})
                _ensure_extension_deps(target)
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'loading'})
                if _load_single_extension(ext_id):
                    ext_data = extensions.get(ext_id)
                    if ext_data:
                        _start_polling(ext_id, ext_data)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'done'})
                else:
                    err = failed_extensions.get(ext_id, {}).get('loadError', 'Unknown error')
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': str(err)})
            except Exception as e:
                log.error("Background install failed for %s: %s", ext_id, e)
                socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': str(e)})

        t = threading.Thread(target=_bg_install_mkt, args=(ext_id, target, ext_info.get('name', ext_id)), daemon=True)
        t.start()
        log.info("Marketplace installing: %s (background)", ext_id)
        return jsonify({'status': 'installing', 'id': ext_id, 'name': ext_info.get('name', ext_id)})
    except Exception as e:
        shutil.rmtree(target, ignore_errors=True)
        return jsonify({'error': f'Install failed: {e}'}), 500

#  WebSocket 

@socketio.on('connect')
def handle_connect():
    global _client_count
    _client_count += 1
    log.info("WS client connected (%d)", _client_count)
    if latest_update:
        emit('realtime_update', latest_update)

@socketio.on('disconnect')
def handle_disconnect():
    global _client_count
    _client_count = max(0, _client_count - 1)
    log.info("WS client disconnected (%d)", _client_count)

@socketio.on('focus_window')
def handle_focus_window():
    """Bring window to front - triggered by second instance trying to start."""
    emit('focus_window', broadcast=True)
    log.info("Focus window requested from second instance")

def _start_polling(ext_id, ext_data):
    cfg = ext_data['config']
    interval = cfg.get('refresh_interval', 0)
    if cfg.get('realtime', False) and interval > 0 and cfg.get('widgets', []):
        t = threading.Thread(target=_poll_extension, args=(ext_id, ext_data, interval), daemon=True)
        t.start()

def realtime_broadcast():
    for ext_id, ext_data in extensions.items():
        _start_polling(ext_id, ext_data)
    while True:
        time.sleep(3600)

def _poll_extension(ext_id, ext_data, interval_ms):
    inst = ext_data['instance']
    cfg = ext_data['config']
    interval = interval_ms / 1000.0
    next_tick = time.monotonic()
    while True:
        tick = time.monotonic()
        values = {}
        for wDef in cfg.get('widgets', []):
            action = wDef.get('action')
            if not action:
                continue
            try:
                method = getattr(inst, action, None)
                if method:
                    result = method()
                    val = result.get('value') if isinstance(result, dict) else result
                    values[wDef['id']] = val
            except Exception as e:
                log.error("%s/%s: %s", ext_id, action, e)
        if values:
            update = {'ext': ext_id, 'values': values}
            if ext_id == 'system_monitor':
                latest_update.clear()
                latest_update.update(update)
            socketio.emit('realtime_update', update)
        next_tick = max(next_tick + interval, tick + interval)
        remaining = next_tick - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

#  Widget state 

def load_widget_state():
    try:
        with open(WIDGET_STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_widget_state(data):
    os.makedirs(os.path.dirname(WIDGET_STATE_PATH), exist_ok=True)
    with _widget_state_lock:
        # Clean up stale tmp file from a previous crash
        tmp = WIDGET_STATE_PATH + '.tmp'
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        # Atomic write: temp file + rename to prevent corruption
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, WIDGET_STATE_PATH)
        except Exception:
            # Fallback: direct write if atomic fails
            with open(WIDGET_STATE_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

@app.route('/api/widget-state')
def api_get_widget_state():
    try:
        return jsonify(load_widget_state())
    except Exception as e:
        log.error("widget-state GET failed: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/widget-state', methods=['POST'])
def api_set_widget_state():
    try:
        data = request.get_json(silent=True) or {}
        save_widget_state(data)
        return jsonify({'ok': True})
    except Exception as e:
        log.error("widget-state POST failed: %s", e)
        return jsonify({'error': str(e)}), 500

#  Scenes 

ALLOWED_SCENE_IMG = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
MAX_SCENE_IMG_SIZE = 256 * 1024  # 256 KiB

def _migrate_scenes(state):
    """Convert old layout/hidden format to scenes."""
    scenes = {
        'default': {
            'label': '🎮',
            'name': 'Default',
            'image': None,
            'cols': 12,
            'rows': 6,
            'widgets': {}
        }
    }
    old_layout = state.get('layout') or {}
    old_hidden = state.get('hidden') or {}
    for ext_id, pos in old_layout.items():
        scenes['default']['widgets'][ext_id] = {
            'col': pos.get('col', 1), 'row': pos.get('row', 1),
            'w': pos.get('w', 2), 'h': pos.get('h', 2),
            'hidden': ext_id in old_hidden
        }
    for ext_id in old_hidden:
        if ext_id not in scenes['default']['widgets']:
            scenes['default']['widgets'][ext_id] = {
                'col': 1, 'row': 1, 'w': 2, 'h': 2, 'hidden': True
            }
    state['scenes'] = scenes
    state['activeScene'] = 'default'
    # Clean old keys
    state.pop('layout', None)
    state.pop('hidden', None)
    save_widget_state(state)
    return scenes

@app.route('/api/scenes')
def api_get_scenes():
    state = load_widget_state()
    scenes = state.get('scenes')
    if not scenes:
        scenes = _migrate_scenes(state)
    # Ensure scenes have the 'name' field (migration)
    for sid, sc in scenes.items():
        if 'name' not in sc:
            sc['name'] = sid.replace('_', ' ').title()
        if 'cols' not in sc:
            sc['cols'] = 12
        if 'rows' not in sc:
            sc['rows'] = 6
    state['scenes'] = scenes
    active = state.get('activeScene')
    # Ensure active scene exists
    if active not in scenes:
        active = list(scenes.keys())[0] if scenes else None
    return jsonify({'scenes': scenes, 'active': active})

@app.route('/api/scenes', methods=['POST'])
def api_create_scene():
    state = load_widget_state()
    scenes = state.get('scenes')
    if not scenes:
        scenes = _migrate_scenes(state)
    # Build id from existing count
    n = len(scenes) + 1
    sid = f'scene_{n}'
    while sid in scenes:
        n += 1
        sid = f'scene_{n}'
    scenes[sid] = {'label': 'home', 'name': sid.replace('_', ' ').title(), 'image': None, 'cols': 12, 'rows': 6, 'widgets': {}}
    state['scenes'] = scenes
    save_widget_state(state)
    return jsonify({'ok': True, 'id': sid})

@app.route('/api/scenes/<scene_id>', methods=['PUT'])
def api_update_scene(scene_id):
    data = request.get_json(silent=True) or {}
    state = load_widget_state()
    scenes = state.get('scenes') or {}
    if scene_id not in scenes:
        return jsonify({'error': 'Scene not found'}), 404
    if 'label' in data:
        scenes[scene_id]['label'] = data['label']
    if 'name' in data:
        scenes[scene_id]['name'] = data['name']
    if 'image' in data:
        scenes[scene_id]['image'] = data['image']
    if 'cols' in data:
        scenes[scene_id]['cols'] = data['cols']
    if 'rows' in data:
        scenes[scene_id]['rows'] = data['rows']
    state['scenes'] = scenes
    save_widget_state(state)
    return jsonify({'ok': True})

@app.route('/api/scenes/<scene_id>', methods=['DELETE'])
def api_delete_scene(scene_id):
    state = load_widget_state()
    scenes = state.get('scenes') or {}
    if scene_id not in scenes:
        return jsonify({'error': 'Scene not found'}), 404
    if len(scenes) <= 1 or scene_id == 'default':
        return jsonify({'error': 'Cannot delete this scene'}), 400
    del scenes[scene_id]
    if state.get('activeScene') == scene_id:
        keys = list(scenes.keys())
        state['activeScene'] = keys[0]
    state['scenes'] = scenes
    save_widget_state(state)
    return jsonify({'ok': True})

@app.route('/api/scenes/activate', methods=['POST'])
def api_activate_scene():
    data = request.get_json(silent=True) or {}
    sid = data.get('id')
    state = load_widget_state()
    scenes = state.get('scenes') or {}
    if sid not in scenes:
        return jsonify({'error': 'Scene not found'}), 404
    state['activeScene'] = sid
    save_widget_state(state)
    return jsonify({'ok': True})

@app.route('/api/scenes/<scene_id>/widgets', methods=['PUT'])
def api_save_scene_widgets(scene_id):
    data = request.get_json(silent=True) or {}
    state = load_widget_state()
    scenes = state.get('scenes') or {}
    if scene_id not in scenes:
        return jsonify({'error': 'Scene not found'}), 404
    scenes[scene_id]['widgets'] = data.get('widgets', {})
    state['scenes'] = scenes
    save_widget_state(state)
    return jsonify({'ok': True})

@app.route('/api/scenes/upload-image', methods=['POST'])
def api_upload_scene_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file'}), 400
    f = request.files['image']
    if not f.filename:
        return jsonify({'error': 'Empty filename'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_SCENE_IMG:
        return jsonify({'error': f'Invalid format: .{ext}. Allowed: {",".join(sorted(ALLOWED_SCENE_IMG))}'}), 400
    # Read and check size
    data_bytes = f.read()
    if len(data_bytes) > MAX_SCENE_IMG_SIZE:
        return jsonify({'error': f'Image too large (max {MAX_SCENE_IMG_SIZE//1024} KiB)'}), 400
    # Save to DATA_DIR/scenes/ (STATIC_DIR is read-only in .exe)
    name = f'scene_img_{int(time.time()*1000)}.{ext}'
    dest_dir = os.path.join(DATA_DIR, 'scenes')
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    with open(dest, 'wb') as out:
        out.write(data_bytes)
    return jsonify({'ok': True, 'path': f'/api/scenes/image/{name}'})

@app.route('/api/scenes/image/<filename>')
def api_serve_scene_image(filename):
    return send_from_directory(os.path.join(DATA_DIR, 'scenes'), filename)

#  Registry helpers 

def _save_registry():
    registry = {}
    for ext_id, ext_data in extensions.items():
        cfg = ext_data['config']
        registry[ext_id] = {
            'name': cfg.get('name', ext_id),
            'version': cfg.get('version', '1.0'),
            'author': cfg.get('author', ''),
            'category': cfg.get('category', 'general')
        }
    new_content = json.dumps(registry, indent=2)
    try:
        with open(REGISTRY_PATH, encoding='utf-8') as f:
            old_content = f.read()
    except (FileNotFoundError, OSError):
        old_content = ''
    if new_content != old_content:
        with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
            f.write(new_content)
        log.info("Registry saved: %d extensions", len(registry))
    else:
        log.info("Registry unchanged")

#  Restart / Quit 

@app.route('/api/restart', methods=['POST'])
def api_restart():
    log.info("Restart: instant reload triggered")
    
    # Signal all extension load threads to cancel
    _ext_isolation.stop_monitor()
    
    # 1. Fire-and-forget cleanup - don't wait
    def _cleanup_async():
        for ext_id, ext_data in list(extensions.items()):
            inst = ext_data.get('instance')
            if hasattr(inst, 'on_stop'):
                try:
                    inst.on_stop()
                except Exception:
                    pass
        
        # Clear subprocess bridges
        for ext_id in list(extensions.keys()):
            _ext_isolation.mark_dead(ext_id, 'Restart')
    
    threading.Thread(target=_cleanup_async, daemon=True, name='restart-cleanup').start()
    
    # 2. Instant state clear - immediate response
    extensions.clear()
    failed_extensions.clear()
    latest_update.clear()
    
    # 3. Remove extension modules from sys.modules
    mods_to_del = [k for k in list(sys.modules.keys()) if k.startswith('extensions.')]
    for k in mods_to_del:
        del sys.modules[k]
    
    # 4. Restart isolation manager and reload extensions (async)
    _ext_isolation.__init__()  # Reset isolation manager
    _ext_isolation.start_monitor()
    load_extensions()
    
    # 5. Rebuild registry (async)
    threading.Thread(target=_save_registry, daemon=True).start()
    
    log.info("Restart: instant response sent, %d extensions loading async", len(extensions))
    return jsonify({'ok': True, 'status': 'reloading'})

@app.route('/api/quit', methods=['POST'])
def api_quit():
    log.info("Shutting down gracefully...")
    socketio.stop()
    time.sleep(0.5)
    for ext in extensions.values():
        inst = ext.get('instance')
        if hasattr(inst, 'on_stop'):
            try:
                inst.on_stop()
            except Exception as e:
                print(f"[-] Extension cleanup error: {e}")
    import signal
    os.kill(os.getpid(), signal.SIGTERM)

#  Startup 

def _sigint_handler(signum, frame):
    log.info("Shutting down...")
    _ext_isolation.stop_monitor()
    os._exit(0)

def start_server(host='127.0.0.1', port=8420, debug=False):
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _sigint_handler)

    # Silence engineio/socketio packet noise, keep werkzeug requests visible in debug
    logging.getLogger('socketio').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)
    logging.getLogger('socketio.server').setLevel(logging.WARNING)
    logging.getLogger('engineio.server').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.DEBUG if debug else logging.WARNING)

    log.info("Starting server (instant mode)...")
    # Start extensions async - non-blocking!
    threading.Thread(target=load_extensions, daemon=True, name='ext-initial-load').start()
    _save_registry()
    rt_thread = threading.Thread(target=realtime_broadcast, daemon=True)
    rt_thread.start()
    log.info("Server running at http://%s:%s", host, port)
    try:
        socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True, log_output=False)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down...")
        _ext_isolation.stop_monitor()
        os._exit(0)

if __name__ == '__main__':
    start_server(debug=True)
