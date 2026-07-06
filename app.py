import io
import os
import json
import hashlib
import logging
import importlib.util
import signal
import subprocess
import sys
import threading
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_socketio import SocketIO, emit

# Force bundle eventlet for PyInstaller (needed by flask-socketio)
try:
    import eventlet
except ImportError:
    pass

# ── Paths ──────────────────────────────────────────────────────────────────

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if sys.platform.startswith('win'):
    DATA_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'CoreFrame')
else:
    DATA_DIR = os.path.join(os.path.expanduser('~'), '.local', 'share', 'CoreFrame')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
EXTENSIONS_DIR = os.path.join(DATA_DIR, 'extensions')
REGISTRY_PATH = os.path.join(DATA_DIR, 'extensions.json')
WIDGET_STATE_PATH = os.path.join(DATA_DIR, 'widget_state.json')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXTENSIONS_DIR, exist_ok=True)

LOG_PATH = os.path.join(DATA_DIR, 'coreframe.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('CoreFrame')

# ── Flask ──────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = hashlib.sha256(os.urandom(32)).hexdigest()
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=["http://127.0.0.1:5000", "http://localhost:5000", "http://127.0.0.1:8420", "http://localhost:8420"])

_LOCAL_TOKEN = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
extensions = {}
latest_update = {}
_client_count = 0

# ── Extension loading ──────────────────────────────────────────────────────

def load_extensions():
    if not os.path.exists(EXTENSIONS_DIR):
        return
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
            spec = importlib.util.spec_from_file_location(f"extensions.{name}", main_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"extensions.{name}"] = module
            spec.loader.exec_module(module)
            ext_instance = module.Extension(config)
            extensions[name] = {'config': config, 'instance': ext_instance}
            log.info("Loaded extension: %s", config.get('name', name))
        except Exception as e:
            log.error("Failed to load %s: %s", name, e)

def _load_single_extension(ext_id):
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    config_path = os.path.join(ext_path, 'extension.json')
    main_path = os.path.join(ext_path, 'main.py')
    if not os.path.exists(config_path) or not os.path.exists(main_path):
        return False
    try:
        with open(config_path, encoding='utf-8-sig') as f:
            config = json.load(f)
        mod_name = f"extensions.{ext_id}"
        spec = importlib.util.spec_from_file_location(mod_name, main_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        ext_instance = module.Extension(config)
        extensions[ext_id] = {'config': config, 'instance': ext_instance}
        log.info("Dynamically loaded extension: %s", config.get('name', ext_id))
        return True
    except Exception as e:
        log.error("Failed to dynamically load %s: %s", ext_id, e)
        return False

# ── Auth ───────────────────────────────────────────────────────────────────

@app.route('/api/token')
def api_token():
    return jsonify({'token': _LOCAL_TOKEN})

@app.before_request
def check_token():
    if request.path.startswith('/api/') and request.path not in ('/api/token', '/api/health'):
        if request.path.startswith('/api/package_extension/'):
            return
        token = request.headers.get('X-CoreFrame-Token', '')
        if token != _LOCAL_TOKEN:
            return jsonify({'error': 'Unauthorized'}), 403

# ── Extension info ─────────────────────────────────────────────────────────

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
            'js_modules': cfg.get('js_modules', []),
            'css_modules': cfg.get('css_modules', [])
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
    return send_from_directory(os.path.join(ext_dir, 'static'), path)

# ── Install extension ──────────────────────────────────────────────────────

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
            return jsonify({'error': f'Extension "{ext_id}" already exists'}), 400
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
        _load_single_extension(ext_id)
        return jsonify({'value': {'name': ext_name, 'id': ext_id, 'installing_deps': False}})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Static frontend ────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(STATIC_DIR, path)

# ── Package extension ──────────────────────────────────────────────────────

@app.route('/api/package_extension/<ext_id>')
def api_package_extension(ext_id):
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    if not os.path.isdir(ext_path):
        return jsonify({'error': 'Extension not found'}), 404
    try:
        buf = io.BytesIO()
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
                    zf.write(full, rel)
        buf.seek(0)
        return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{ext_id}.zip')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── WebSocket ──────────────────────────────────────────────────────────────

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

def realtime_broadcast():
    for ext_id, ext_data in extensions.items():
        cfg = ext_data['config']
        interval = cfg.get('refresh_interval', 0)
        if cfg.get('realtime', False) and interval > 0 and cfg.get('widgets', []):
            t = threading.Thread(target=_poll_extension, args=(ext_id, ext_data, interval), daemon=True)
            t.start()
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

# ── Widget state ───────────────────────────────────────────────────────────

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

# ── Restart / Quit ─────────────────────────────────────────────────────────

@app.route('/api/restart', methods=['POST'])
def api_restart():
    threading.Timer(0.5, lambda: [subprocess.Popen([sys.executable] + sys.argv), os._exit(0)]).start()
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

# ── Startup ────────────────────────────────────────────────────────────────

def _sigint_handler(signum, frame):
    log.info("Shutting down...")
    os._exit(0)

def start_server(host='127.0.0.1', port=5000, debug=False):
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
    start_server()
