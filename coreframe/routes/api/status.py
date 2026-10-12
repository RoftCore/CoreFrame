from flask import jsonify
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.extensions.permissions import get_permission_manager

def _ext_payload(ext_id, cfg, perm_info, **extra):
    """Single builder for every extension state, so a manifest field cannot be added to the loaded list and forgotten in the others."""
    payload = {
        'id': ext_id,
        'name': cfg.get('name', ext_id),
        'icon': cfg.get('icon', ''),
        'category': cfg.get('category', 'general'),
        'menu_items': cfg.get('menu_items', []),
        'widgets': cfg.get('widgets', []),
        'grid_size': cfg.get('grid_size'),
        'overlayable': cfg.get('overlayable', False),
        'keep_alive': cfg.get('keep_alive', True),
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
        'hideScrollbar': cfg.get('hideScrollbar', False),
        # Core-owned appearance animation. Absent means "use the core default",
        # which is the whole point: extensions should not each ship their own
        # entrance animation, they only get the chance to opt out or pick
        # another one from the palette the core defines.
        'appear_animation': cfg.get('appear_animation'),
        'permissions': perm_info,
    }
    payload.update(extra)
    return payload


def register_status_routes(app, socketio):
    """Register the status API routes."""
    @app.route('/api/extensions')
    def api_extensions():
        from coreframe.extensions.loader import denied_consent
        # Opens the load gate so the host receives "pending" entries and can reserve the grid while loading.
        try:
            from coreframe.extensions.loader import request_initial_load
            request_initial_load()
        except Exception:
            pass
        perm = get_permission_manager()
        result = {}
        for ext_id, ext_data in extensions.items():
            cfg = ext_data['config']
            result[ext_id] = _ext_payload(
                ext_id, cfg, perm.get_permission_info(cfg),
                consent_granted=perm.has_consent(ext_id))
        for ext_id, ext_data in failed_extensions.items():
            cfg = ext_data.get('config', {})
            perm_info = perm.get_permission_info(cfg) if cfg else {'level': -1, 'level_name': 'unknown'}
            result[ext_id] = {
                'id': ext_id,
                'name': ext_data.get('name', ext_id),
                'loadError': ext_data.get('loadError', 'Unknown error'),
                'widgets': [],
                'permissions': perm_info,
                'consent_granted': False,
            }
        # Still loading: report the manifest so the host reserves the grid slot immediately.
        from coreframe.extensions.loader import pending_manifests
        for ext_id, cfg in pending_manifests().items():
            if ext_id in result:
                continue
            payload = _ext_payload(ext_id, cfg,
                                   perm.get_permission_info(cfg),
                                   consent_granted=perm.has_consent(ext_id))
            payload['pending'] = True
            result[ext_id] = payload
        # Disabled extensions: installed and registered, but not running. They
        # are listed with widgets emptied so the host renders no card for them.
        from coreframe.extensions.loader import disabled_extensions as _disabled
        for ext_id, info in _disabled.items():
            if ext_id in result:
                continue
            cfg = info.get('config', {})
            payload = _ext_payload(ext_id, cfg,
                                   perm.get_permission_info(cfg) if cfg else {'level': -1, 'level_name': 'unknown'},
                                   consent_granted=perm.has_consent(ext_id))
            payload['disabled'] = True
            payload['widgets'] = []
            result[ext_id] = payload

        # Denied and pending extensions are listed too: not loaded, still visible
        from coreframe.extensions.loader import pending_consent as _pending
        for source in (denied_consent, _pending):
            for ext_id, info in source.items():
                if ext_id in result:
                    continue
                cfg = info.get('config', {})
                result[ext_id] = _ext_payload(
                    ext_id, cfg, perm.get_permission_info(cfg),
                    consent_granted=False, consent_denied=True,
                    loadError='Consent denied by user')
        return jsonify(result)

    @app.route('/api/health')
    def api_health():
        from coreframe.websocket import _client_count
        return jsonify({
            'status': 'ok',
            'extensions': len(extensions),
            'clients': _client_count,
        })

    @app.route('/api/debug/pollers')
    def api_debug_pollers():
        """Which realtime pollers are alive and when they last emitted."""
        from coreframe.extensions.loader import pollers_status
        return jsonify(pollers_status())

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
        # Server-level emit (works from plain HTTP context — the bare
        # flask_socketio.emit() shortcut only works inside socket handlers
        # and 500s here). No room => delivered to all clients.
        # Frontend core.js relays it to pywebview focus.
        # NOTE: no broadcast= kwarg — this python-socketio version rejects it.
        socketio.emit('focus_window')
        return jsonify({'ok': True})

