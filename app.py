import os
import json
import hashlib
import importlib.util
import sys
import threading
import time
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
EXTENSIONS_DIR = os.path.join(BASE_DIR, 'extensions')

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = hashlib.sha256(os.urandom(32)).hexdigest()
socketio = SocketIO(app, cors_allowed_origins=["http://127.0.0.1:5000", "http://localhost:5000"])

# Token local generado al arrancar para proteger APIs
_LOCAL_TOKEN = hashlib.sha256(os.urandom(32)).hexdigest()[:16]

extensions = {}
latest_update = {}
_client_count = 0

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
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
            spec = importlib.util.spec_from_file_location(f"extensions.{name}", main_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"extensions.{name}"] = module
            spec.loader.exec_module(module)
            ext_instance = module.Extension(config)
            extensions[name] = {'config': config, 'instance': ext_instance}
            print(f"[+] Loaded extension: {config.get('name', name)}")
        except Exception as e:
            print(f"[-] Failed to load {name}: {e}")

@app.route('/api/token')
def api_token():
    return jsonify({'token': _LOCAL_TOKEN})

@app.before_request
def check_token():
    if request.path.startswith('/api/') and request.path != '/api/token':
        token = request.headers.get('X-CoreFrame-Token', '')
        if token != _LOCAL_TOKEN:
            return jsonify({'error': 'Unauthorized'}), 403

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

@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(STATIC_DIR, path)

@socketio.on('connect')
def handle_connect():
    global _client_count
    _client_count += 1
    print(f'[WS] Client connected ({_client_count})')
    if latest_update:
        emit('realtime_update', latest_update)

@socketio.on('disconnect')
def handle_disconnect():
    global _client_count
    _client_count = max(0, _client_count - 1)
    print(f'[WS] Client disconnected ({_client_count})')

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
                print(f"[-] {ext_id}/{action}: {e}")
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

WIDGET_STATE_PATH = os.path.join(BASE_DIR, 'widget_state.json')

def load_widget_state():
    try:
        with open(WIDGET_STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_widget_state(data):
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

@app.route('/api/restart', methods=['POST'])
def api_restart():
    import subprocess, threading
    threading.Timer(0.5, lambda: [subprocess.Popen([sys.executable] + sys.argv), os._exit(0)]).start()
    return jsonify({'ok': True})

@app.route('/api/quit', methods=['POST'])
def api_quit():
    print("[*] Shutting down gracefully...")
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

if __name__ == '__main__':
    print("[*] CoreFrame - Loading extensions...")
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
    registry_path = os.path.join(BASE_DIR, 'extensions.json')
    new_content = json.dumps(registry, indent=2)
    try:
        with open(registry_path, encoding='utf-8') as f:
            old_content = f.read()
    except (FileNotFoundError, OSError):
        old_content = ''
    if new_content != old_content:
        with open(registry_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[*] Registry saved: {len(registry)} extensions")
    else:
        print(f"[*] Registry unchanged")
    rt_thread = threading.Thread(target=realtime_broadcast, daemon=True)
    rt_thread.start()
    print("[*] Server running at http://127.0.0.1:5000")
    socketio.run(app, host='127.0.0.1', port=5000, debug=False)
