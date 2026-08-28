import os
import sys
import hashlib
import signal
import threading

from flask import Flask
from flask_socketio import SocketIO

from coreframe.config import log, STATIC_DIR, EXTENSIONS_DIR, REGISTRY_PATH
from coreframe.auth import init_auth, register_auth_routes
from coreframe.extensions import _ext_isolation, load_extensions
from coreframe.routes import (
    register_api_routes, register_install_routes, register_marketplace_routes,
    register_scene_routes, register_widget_routes, register_static_routes,
)
from coreframe.websocket import register_websocket_handlers
from coreframe.routes.widgets import load_widget_state

import shutil

# ── Extract bundled extensions ─────────────────────────────────────

if getattr(sys, 'frozen', False):
    from coreframe.config import BASE_DIR, DATA_DIR
    _bundled_ext_dir = os.path.join(BASE_DIR, 'extensions')
    if os.path.isdir(_bundled_ext_dir):
        for _name in os.listdir(_bundled_ext_dir):
            _src = os.path.join(_bundled_ext_dir, _name)
            _dst = os.path.join(EXTENSIONS_DIR, _name)
            if os.path.isdir(_src) and not os.path.exists(_dst):
                shutil.copytree(_src, _dst, ignore_dangling_symlinks=True)
                log.info("Extracted bundled extension: %s", _name)

# ── Flask + SocketIO ──────────────────────────────────────────────

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = hashlib.sha256(os.urandom(32)).hexdigest()
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=["http://127.0.0.1:8420", "http://localhost:8420"])

# ── Auth ───────────────────────────────────────────────────────────

_LOCAL_TOKEN = init_auth(app)

# ── Register routes ────────────────────────────────────────────────

register_auth_routes(app)
register_api_routes(app)
register_install_routes(app, socketio)
register_marketplace_routes(app, socketio)
register_scene_routes(app)
register_widget_routes(app)
register_static_routes(app)
register_websocket_handlers(socketio, _ext_isolation)

# ── Registry ───────────────────────────────────────────────────────

from coreframe.extensions import extensions


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
    import json
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


# ── Restart / Quit ─────────────────────────────────────────────────

@app.route('/api/restart', methods=['POST'])
def api_restart():
    log.info("Restart: instant reload triggered")

    _ext_isolation.stop_monitor()

    def _cleanup_async():
        for ext_id, ext_data in list(extensions.items()):
            inst = ext_data.get('instance')
            if hasattr(inst, 'on_stop'):
                try:
                    inst.on_stop()
                except Exception:
                    pass
        for ext_id in list(extensions.keys()):
            _ext_isolation.mark_dead(ext_id, 'Restart')

    threading.Thread(target=_cleanup_async, daemon=True, name='restart-cleanup').start()

    extensions.clear()
    from coreframe.extensions import failed_extensions
    failed_extensions.clear()
    from coreframe.websocket import latest_update
    latest_update.clear()

    mods_to_del = [k for k in list(sys.modules.keys()) if k.startswith('extensions.')]
    for k in mods_to_del:
        del sys.modules[k]

    _ext_isolation.stop_monitor()
    _ext_isolation.__init__()
    _ext_isolation.start_monitor()
    load_extensions()

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


# ── Startup ────────────────────────────────────────────────────────

def _sigint_handler(signum, frame):
    log.info("Shutting down...")
    _ext_isolation.stop_monitor()
    os._exit(0)


_shutdown_callback = None  # Set by run_coreframe.pyw


def start_server(host='127.0.0.1', port=8420, debug=False):
    import logging as _logging
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _sigint_handler)

    _logging.getLogger('socketio').setLevel(_logging.WARNING)
    _logging.getLogger('engineio').setLevel(_logging.WARNING)
    _logging.getLogger('socketio.server').setLevel(_logging.WARNING)
    _logging.getLogger('engineio.server').setLevel(_logging.WARNING)
    _logging.getLogger('werkzeug').setLevel(_logging.DEBUG if debug else _logging.WARNING)

    log.info("Starting server (instant mode)...")
    threading.Thread(target=load_extensions, daemon=True, name='ext-initial-load').start()
    _save_registry()
    from coreframe.websocket import realtime_broadcast
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
