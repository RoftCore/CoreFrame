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
        # Log the call
        try:
            _cmd = args[0] if args else kwargs.get('args', '?')
            if isinstance(_cmd, (list, tuple)):
                _cmd = ' '.join(str(x) for x in _cmd)
            import builtins as _b
            _b.print(f"[POPEN] old=0x{old:08x} new=0x{newflags:08x} cmd={_cmd[:200]}", flush=True)
        except Exception:
            pass
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

#  Core packages — excluded from lib bundling (CoreFrame's own deps) 
CORE_PACKAGES = {
    'flask', 'flask_socketio', 'flask_cors', 'flask_limiter',
    'eventlet', 'bottle',
    'requests', 'requests_toolbelt', 'urllib3', 'chardet', 'certifi', 'idna',
    'python_socketio', 'python_engineio',
    'markupsafe', 'jinja2', 'werkzeug', 'itsdangerous',
    'importlib_metadata', 'zipp', 'typing_extensions',
    'pip', 'setuptools', 'wheel',
}

def _bundle_dependencies(ext_path, zf):
    req_path = os.path.join(ext_path, 'requirements.txt')
    if not os.path.exists(req_path):
        return
    with open(req_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            raw_pkg = re.split(r'[>=<~!]', line)[0].strip()
            import_name = raw_pkg.lower().replace('-', '_').replace('.', '_')
            if import_name in CORE_PACKAGES:
                continue
            try:
                spec = importlib.util.find_spec(import_name)
                if not spec or not spec.origin:
                    continue
                if spec.submodule_search_locations:
                    pkg_root = spec.submodule_search_locations[0]
                else:
                    pkg_root = spec.origin
                site_pkgs = os.path.dirname(pkg_root)
                def _write_to_zip(src_path):
                    rel = os.path.relpath(src_path, site_pkgs)
                    arc = os.path.join('lib', rel)
                    try:
                        zf.getinfo(arc)
                    except KeyError:
                        zf.write(src_path, arc)
                if os.path.isdir(pkg_root):
                    for root, _dirs, files in os.walk(pkg_root, followlinks=True):
                        for f in files:
                            _write_to_zip(os.path.join(root, f))
                    # top-level files (single .py modules at the same level)
                    for entry in os.listdir(site_pkgs):
                        if entry.startswith(os.path.basename(pkg_root) + '.') and entry.endswith('.py'):
                            _write_to_zip(os.path.join(site_pkgs, entry))
                else:
                    _write_to_zip(pkg_root)
                # dist-info
                dist_info_dir = os.path.join(site_pkgs, os.path.basename(pkg_root) + '.dist-info')
                if os.path.isdir(dist_info_dir):
                    for root, _dirs, files in os.walk(dist_info_dir):
                        for f in files:
                            _write_to_zip(os.path.join(root, f))
            except Exception:
                pass

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
SHARED_LIB_DIR = os.path.join(DATA_DIR, 'lib')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXTENSIONS_DIR, exist_ok=True)
os.makedirs(SHARED_LIB_DIR, exist_ok=True)

MARKETPLACE_URL = 'https://raw.githubusercontent.com/RoftCore/extensions-coreframe/main/registry.json'
if SHARED_LIB_DIR not in sys.path:
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

def load_extensions():
    log.info("load_extensions: EXTENSIONS_DIR=%s exists=%s", EXTENSIONS_DIR, os.path.exists(EXTENSIONS_DIR))
    if not os.path.exists(EXTENSIONS_DIR):
        return
    current_os = 'linux' if not sys.platform.startswith('win') else 'windows'
    for name in os.listdir(EXTENSIONS_DIR):
        ext_path = os.path.join(EXTENSIONS_DIR, name)
        if not os.path.isdir(ext_path):
            continue
        config_path = os.path.join(ext_path, 'extension.json')
        main_path = os.path.join(ext_path, 'main.py')
        if not os.path.exists(config_path) or not os.path.exists(main_path):
            continue
        try:
            with open(config_path, encoding='utf-8-sig') as f:
                config = json.load(f)
            platforms = config.get('platforms')
            if platforms is not None and current_os not in platforms:
                log.info("Skipping %s: not compatible with %s", name, current_os)
                continue
            _sync_extension_lib(ext_path)
            lang = config.get('language', 'python')
            if lang != 'python' and lang != 'py':
                ext_instance = SubprocessBridge(config, ext_path)
            else:
                spec = importlib.util.spec_from_file_location(f"extensions.{name}", main_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"extensions.{name}"] = module
                spec.loader.exec_module(module)
                ext_instance = module.Extension(config)
            extensions[name] = {'config': config, 'instance': ext_instance}
            log.info("Loaded extension: %s (%s)", config.get('name', name), lang)
        except json.JSONDecodeError as e:
            msg = f"Invalid extension.json: {e}"
            log.error("Failed to load %s: %s", name, msg)
            failed_extensions[name] = {'name': name, 'loadError': msg}
        except Exception as e:
            msg = str(e)
            log.error("Failed to load %s: %s", name, msg)
            try:
                with open(config_path, encoding='utf-8-sig') as f:
                    config = json.load(f)
                failed_extensions[name] = {'name': config.get('name', name), 'loadError': msg}
            except Exception:
                failed_extensions[name] = {'name': name, 'loadError': msg}

def _load_single_extension(ext_id):
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    config_path = os.path.join(ext_path, 'extension.json')
    main_path = os.path.join(ext_path, 'main.py')
    if not os.path.exists(config_path):
        return False
    try:
        with open(config_path, encoding='utf-8-sig') as f:
            config = json.load(f)
        lang = config.get('language', 'python')
        _sync_extension_lib(ext_path)
        if lang != 'python' and lang != 'py':
            ext_instance = SubprocessBridge(config, ext_path)
        else:
            if not os.path.exists(main_path):
                return False
            mod_name = f"extensions.{ext_id}"
            spec = importlib.util.spec_from_file_location(mod_name, main_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            ext_instance = module.Extension(config)
        extensions[ext_id] = {'config': config, 'instance': ext_instance}
        failed_extensions.pop(ext_id, None)
        log.info("Dynamically loaded extension: %s (%s)", config.get('name', ext_id), lang)
        return True
    except Exception as e:
        log.error("Failed to dynamically load %s: %s", ext_id, e)
        return False

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
        log.info("[Bridge] Started %s process for %s (pid=%d)", self.language, self.ext_id, self._proc.pid)
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name=f'bridge-{self.ext_id}')
        self._reader.start()

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
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()

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
                winreg.SetValueEx(key, AUTOSTART_KEY, 0, winreg.REG_SZ, sys.executable)
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
                    f'Exec={sys.executable}\n'
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
        if os.path.exists(target):
            return jsonify({'exists': True, 'message': f'Extension "{ext_name}" has already been imported before and cannot be imported again.'})
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

        # Load immediately — no pip steps, no polling needed
        if not _load_single_extension(ext_id):
            err_msg = failed_extensions.get(ext_id, {}).get('loadError', 'Unknown error')
            return jsonify({'error': f'Extension installed but failed to load: {err_msg}'}), 500
        ext_data = extensions.get(ext_id)
        if ext_data:
            _start_polling(ext_id, ext_data)
        return jsonify({'value': {'name': ext_name, 'id': ext_id, 'installing_deps': False}})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extensions/<ext_id>', methods=['DELETE'])
def api_delete_extension(ext_id):
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    if not os.path.isdir(ext_path):
        return jsonify({'error': 'Extension not found'}), 404

    try:
        shutil.rmtree(ext_path)
    except Exception as e:
        return jsonify({'error': f'Failed to delete extension files: {e}'}), 500

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

            # Bundle required libraries (from requirements.txt, minus core packages)
            _bundle_dependencies(ext_path, zf)

            # Ensure lib/ subdirectories have __init__.py
            ext_lib = os.path.join(ext_path, 'lib')
            if os.path.isdir(ext_lib):
                for sub_root, sub_dirs, sub_files in os.walk(ext_lib):
                    for sd in sub_dirs:
                        init_path = os.path.join(sub_root, sd, '__init__.py')
                        rel_init = os.path.relpath(init_path, ext_path).replace('\\', '/')
                        # Only add if not already present in the walk
                        try:
                            zf.getinfo(rel_init)
                        except KeyError:
                            zf.writestr(rel_init, '')

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
    if os.path.exists(target):
        return jsonify({'exists': True, 'message': f'Extension "{ext_info.get("name", ext_id)}" has already been imported before and cannot be imported again.'})

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
        _load_single_extension(ext_id)
        ext_data = extensions.get(ext_id)
        if ext_data:
            _start_polling(ext_id, ext_data)
        log.info("Marketplace installed: %s v%s", ext_id, ext_info.get('version', '?'))
        return jsonify({'ok': True, 'name': ext_info.get('name', ext_id)})
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
    with open(WIDGET_STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

@app.route('/api/widget-state')
def api_get_widget_state():
    return jsonify(load_widget_state())

@app.route('/api/widget-state', methods=['POST'])
def api_set_widget_state():
    data = request.get_json(silent=True) or {}
    save_widget_state(data)
    return jsonify({'ok': True})

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

#  Restart / Quit 

@app.route('/api/restart', methods=['POST'])
def api_restart():
    threading.Timer(0.5, lambda: [subprocess.Popen([sys.executable] + sys.argv, creationflags=subprocess.CREATE_NO_WINDOW), os._exit(0)]).start()
    return jsonify({'ok': True})

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

    log.info("Loading extensions...")
    load_extensions()
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
    rt_thread = threading.Thread(target=realtime_broadcast, daemon=True)
    rt_thread.start()
    log.info("Server running at http://%s:%s", host, port)
    try:
        socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True, log_output=False)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down...")
        os._exit(0)

if __name__ == '__main__':
    start_server(debug=True)
