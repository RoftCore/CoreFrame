import os
from flask import jsonify, request

from coreframe.config import EXTENSIONS_DIR
from coreframe.extensions import extensions, failed_extensions, _ext_isolation


def register_api_routes(app):

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
        from coreframe.websocket import _client_count
        return jsonify({
            'status': 'ok',
            'extensions': len(extensions),
            'clients': _client_count,
        })

    @app.route('/api/extensions/health')
    def api_extensions_health():
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
        if ext_id not in extensions:
            return jsonify({'error': 'Extension not loaded'}), 404
        _ext_isolation.heartbeat(ext_id)
        return jsonify({'ok': True})

    @app.route('/api/window/focus', methods=['POST'])
    def api_window_focus():
        from flask_socketio import emit
        emit('focus_window')
        return jsonify({'ok': True})

    @app.route('/api/extension/<ext_id>/<action>', methods=['GET', 'POST'])
    def api_extension_action(ext_id, action):
        if ext_id not in extensions:
            return jsonify({'error': 'Extension not found'}), 404
        if action.startswith('_') or action.startswith('__'):
            return jsonify({'error': 'Action not allowed'}), 403
        try:
            ext = extensions[ext_id]['instance']
            method = getattr(ext, action, None)
            if not method:
                return jsonify({'error': f'Action {action} not found'}), 404
            if not callable(method):
                return jsonify({'error': 'Action not callable'}), 400
            if request.method == 'POST':
                result = method(request.get_json(silent=True) or {})
            else:
                result = method()
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/ext-static/<ext_id>/<path:path>')
    def ext_static(ext_id, path):
        from flask import Response, send_from_directory
        if '..' in ext_id or '/' in ext_id or '\\' in ext_id:
            return Response('Invalid extension id', 400)
        ext_dir = os.path.join(EXTENSIONS_DIR, ext_id)
        static_dir = os.path.join(ext_dir, 'static')
        if not os.path.isdir(static_dir):
            return Response('', 204)
        try:
            return send_from_directory(static_dir, path)
        except FileNotFoundError:
            return Response('', 204)

    @app.route('/api/debug')
    def api_debug():
        try:
            ext_dir_contents = os.listdir(EXTENSIONS_DIR) if os.path.isdir(EXTENSIONS_DIR) else []
        except Exception:
            ext_dir_contents = []
        from coreframe.config import DATA_DIR, BASE_DIR
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


