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
app.config['SECRET_KEY'] = 'coreframe-secret'
socketio = SocketIO(app, cors_allowed_origins="http://127.0.0.1:5000")

# Token local generado al arrancar para proteger APIs
_LOCAL_TOKEN = hashlib.sha256(os.urandom(32)).hexdigest()[:16]

extensions = {}
history_cache = {'cpu': [], 'ram': [], 'gpu': [], 'disk': []}
latest_update = {}
MAX_HISTORY = 40
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
            'refresh_interval': cfg.get('refresh_interval', 5000)
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
    if _client_count > 1:
        emit('history', history_cache)
    if latest_update:
        emit('realtime_update', latest_update)

@socketio.on('disconnect')
def handle_disconnect():
    global _client_count
    _client_count = max(0, _client_count - 1)
    print(f'[WS] Client disconnected ({_client_count})')

def realtime_broadcast():
    while True:
        if 'system_monitor' in extensions:
            try:
                inst = extensions['system_monitor']['instance']
                cpu = inst.get_cpu() if hasattr(inst, 'get_cpu') else {}
                ram = inst.get_ram() if hasattr(inst, 'get_ram') else {}
                gpu = inst.get_gpu() if hasattr(inst, 'get_gpu') else {}
                disk = inst.get_disk() if hasattr(inst, 'get_disk') else {}
                
                cpu_val = cpu.get('value')
                ram_val = ram.get('value')
                gpu_val = gpu.get('value')
                disk_val = disk.get('value')

                for key, val in [('cpu', cpu_val), ('ram', ram_val), ('gpu', gpu_val), ('disk', disk_val)]:
                    if val is not None:
                        pct = val if isinstance(val, (int, float)) else (val.get('percent') if isinstance(val, dict) and 'percent' in val else None)
                        if pct is not None:
                            history_cache[key].append(pct)
                            if len(history_cache[key]) > MAX_HISTORY:
                                history_cache[key].pop(0)

                update = {
                    'cpu': cpu_val,
                    'ram': ram_val,
                    'gpu': gpu_val,
                    'disk': disk_val
                }
                latest_update.clear()
                latest_update.update(update)
                socketio.emit('realtime_update', update)
            except:
                pass
        time.sleep(1)

@app.route('/api/quit', methods=['POST'])
def api_quit():
    print("[*] Shutting down...")
    socketio.stop()
    time.sleep(0.5)
    os._exit(0)

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
    with open(os.path.join(BASE_DIR, 'extensions.json'), 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2)
    print(f"[*] Registry saved: {len(registry)} extensions")
    rt_thread = threading.Thread(target=realtime_broadcast, daemon=True)
    rt_thread.start()
    print("[*] Server running at http://127.0.0.1:5000")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)
