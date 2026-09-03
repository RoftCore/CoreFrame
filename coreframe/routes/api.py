import os
import sys
from flask import jsonify, request

from coreframe.config import EXTENSIONS_DIR, REGISTRY_PATH
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.extensions.permissions import (
    get_permission_manager, PERMISSION_LEVELS, PERMISSION_NAMES,
    PERMISSION_LABELS, PERMISSION_DESCRIPTIONS, ESCALATION_METHODS,
)


def register_api_routes(app):

    @app.route('/api/extensions')
    def api_extensions():
        from coreframe.extensions.loader import denied_consent
        perm = get_permission_manager()
        result = {}
        for ext_id, ext_data in extensions.items():
            cfg = ext_data['config']
            perm_info = perm.get_permission_info(cfg)
            consent = perm.has_consent(ext_id)
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
                'hideScrollbar': cfg.get('hideScrollbar', False),
                'permissions': perm_info,
                'consent_granted': consent,
            }
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
        # Include denied extensions (not loaded, but user should see them)
        for ext_id, info in denied_consent.items():
            if ext_id in result:
                continue  # Already in result
            cfg = info.get('config', {})
            perm_info = perm.get_permission_info(cfg)
            result[ext_id] = {
                'id': ext_id,
                'name': info.get('name', ext_id),
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
                'hideScrollbar': cfg.get('hideScrollbar', False),
                'permissions': perm_info,
                'consent_granted': False,
                'consent_denied': True,
                'loadError': 'Consent denied by user',
            }
        # Include pending consent (revoked or needs consent) as paperweight
        from coreframe.extensions.loader import pending_consent as _pending
        for ext_id, info in _pending.items():
            if ext_id in result:
                continue
            cfg = info.get('config', {})
            perm_info = perm.get_permission_info(cfg)
            result[ext_id] = {
                'id': ext_id,
                'name': info.get('name', ext_id),
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
                'hideScrollbar': cfg.get('hideScrollbar', False),
                'permissions': perm_info,
                'consent_granted': False,
                'consent_denied': True,
                'loadError': 'Consent denied by user',
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

        # ── Permission check for base level ────────────────────────
        perm = get_permission_manager()
        ext_config = extensions[ext_id]['config']
        required_level = perm.get_required_level(ext_config)
        if required_level >= 3 and not perm.check(ext_id, required_level):
            return jsonify({
                'error': 'Permission denied',
                'needs_consent': True,
                'required_level': required_level,
                'required_level_name': PERMISSION_NAMES.get(required_level, 'unknown'),
            }), 403

        # ── Escalation check ───────────────────────────────────────
        escalation = perm.get_escalation(ext_config)
        if escalation:
            for esc_level_str, esc_rules in escalation.items():
                esc_level = PERMISSION_LEVELS.get(esc_level_str, 5)
                methods = esc_rules.get('methods', [])
                if action in methods:
                    if not perm.check_escalation(ext_id, action):
                        # Ask for escalation
                        perm.emit_escalation_request(
                            ext_id,
                            ext_config.get('name', ext_id),
                            action,
                            esc_level,
                        )
                        return jsonify({
                            'error': 'Escalation required',
                            'needs_escalation': True,
                            'method': action,
                            'escalation_level': esc_level,
                            'escalation_level_name': PERMISSION_NAMES.get(esc_level, 'unknown'),
                        }), 403

        # ── File path validation for file operations ────────────────
        _FILE_METHODS = {'write_file', 'edit_file', 'replace_file', 'delete_file', 'list_dir', 'read_file'}
        if action in _FILE_METHODS:
            data = request.get_json(silent=True) or {}
            path = data.get('path', '')
            if path:
                from coreframe.extensions.security import validate_api_path
                allowed, err = validate_api_path(ext_id, path, action)
                if not allowed:
                    return jsonify({'error': err}), 403

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

    # ── Permission management routes ───────────────────────────────

    @app.route('/api/extensions/permissions')
    def api_permissions_list():
        """List all permissions and consents."""
        perm = get_permission_manager()
        return jsonify({
            'consents': perm.get_all_consents(),
            'levels': PERMISSION_LEVELS,
            'level_names': PERMISSION_NAMES,
            'level_labels': PERMISSION_LABELS,
            'descriptions': PERMISSION_DESCRIPTIONS,
        })

    @app.route('/api/extensions/<ext_id>/permissions')
    def api_permissions_info(ext_id):
        """Get permission info for a specific extension."""
        perm = get_permission_manager()
        config = {}
        if ext_id in extensions:
            config = extensions[ext_id]['config']
        elif ext_id in failed_extensions:
            config = failed_extensions[ext_id].get('config', {})

        if not config:
            return jsonify({'error': 'Extension not found'}), 404

        perm_info = perm.get_permission_info(config)
        perm_info['consent_granted'] = perm.has_consent(ext_id)
        if perm.has_consent(ext_id):
            perm_info['granted_level'] = perm.get_granted_level(ext_id)
            perm_info['granted_escalations'] = perm.get_granted_escalations(ext_id)
        perm_info['whitelist'] = perm.get_whitelist(ext_id)
        return jsonify(perm_info)

    @app.route('/api/extensions/<ext_id>/permissions/grant', methods=['POST'])
    def api_permissions_grant(ext_id):
        """Grant consent and load the extension."""
        from coreframe.extensions.loader import pending_consent, denied_consent, load_after_consent
        from coreframe.extensions.security import restore_consent_files, protect_consent_files
        perm = get_permission_manager()
        data = request.get_json(silent=True) or {}
        level = data.get('level')
        escalations = data.get('escalations', [])

        if level is None:
            return jsonify({'error': 'level is required'}), 400

        if isinstance(level, str):
            level = PERMISSION_LEVELS.get(level, 0)

        restore_consent_files()
        try:
            perm.grant(ext_id, level, escalations)
            # Clear denied state if it was denied before
            perm.clear_denied(ext_id)
            denied_consent.pop(ext_id, None)
        finally:
            protect_consent_files()

        # If this extension was pending consent, load it now
        loaded = False
        if ext_id in pending_consent:
            loaded = load_after_consent(ext_id)

        return jsonify({'ok': True, 'level': level, 'loaded': loaded})

    @app.route('/api/extensions/<ext_id>/permissions/revoke', methods=['POST'])
    def api_permissions_revoke(ext_id):
        """Revoke all permissions from an extension — keep as paperweight in extensions list, only hide from viewport."""
        from coreframe.extensions.loader import denied_consent, pending_consent, extensions, _poll_stop_events, _ext_isolation
        from coreframe.extensions.security import restore_consent_files, protect_consent_files
        perm = get_permission_manager()
        restore_consent_files()
        try:
            perm.revoke(ext_id)
            denied_consent.pop(ext_id, None)
            # Move running extension to pending_consent as paperweight and stop it
            if ext_id in extensions:
                ext_data = extensions.pop(ext_id)
                cfg = ext_data.get('config', {})
                # Stop polling
                ev = _poll_stop_events.pop(ext_id, None)
                if ev:
                    try:
                        ev.set()
                    except Exception:
                        pass
                # Stop instance (bridge or in-process)
                inst = ext_data.get('instance')
                if inst:
                    try:
                        if hasattr(inst, 'on_stop'):
                            inst.on_stop()
                        elif hasattr(inst, 'stop'):
                            inst.stop()
                    except Exception:
                        pass
                    try:
                        _ext_isolation.mark_dead(ext_id, 'Revoked by user')
                    except Exception:
                        pass
                # Keep as pending so it stays in extensions list as paperweight (only viewport hidden)
                if ext_id not in pending_consent:
                    pending_consent[ext_id] = {
                        'name': cfg.get('name', ext_id),
                        'config': cfg,
                        'path': cfg.get('__ext_path', ''),
                        'level': perm.get_required_level(cfg),
                    }
                    # Ensure __ext_path is set for reload
                    if not pending_consent[ext_id]['path']:
                        from coreframe.config import EXTENSIONS_DIR
                        pending_consent[ext_id]['path'] = os.path.join(EXTENSIONS_DIR, ext_id)
        finally:
            protect_consent_files()
        return jsonify({'ok': True})

    @app.route('/api/extensions/<ext_id>/permissions/deny', methods=['POST'])
    def api_permissions_deny(ext_id):
        """Persist consent denial for an extension."""
        from coreframe.extensions.loader import pending_consent, denied_consent
        from coreframe.extensions.security import restore_consent_files, protect_consent_files
        perm = get_permission_manager()
        restore_consent_files()
        try:
            ext_name = pending_consent.get(ext_id, {}).get('name', ext_id)
            level = pending_consent.get(ext_id, {}).get('level', 0)
            perm.mark_denied(ext_id, ext_name, level)
            denied_consent[ext_id] = pending_consent.get(ext_id, {})
            pending_consent.pop(ext_id, None)
        finally:
            protect_consent_files()
        return jsonify({'ok': True})

    @app.route('/api/extensions/<ext_id>/permissions/check')
    def api_permissions_check(ext_id):
        """Check consent status for an extension. Returns whether consent is needed."""
        from coreframe.extensions.loader import pending_consent, denied_consent
        perm = get_permission_manager()

        # Already granted
        if perm.has_consent(ext_id):
            return jsonify({'status': 'granted', 'has_consent': True})

        # Currently pending (modal should show)
        if ext_id in pending_consent:
            info = pending_consent[ext_id]
            return jsonify({
                'status': 'pending',
                'has_consent': False,
                'level': info.get('level', 3),
                'name': info.get('name', ext_id),
            })

        # Previously denied
        if perm.is_denied(ext_id) or ext_id in denied_consent:
            info = denied_consent.get(ext_id, {})
            return jsonify({
                'status': 'denied',
                'has_consent': False,
                'level': info.get('level', 3),
                'name': info.get('name', ext_id),
            })

        # Low level, no consent needed
        return jsonify({'status': 'granted', 'has_consent': True})

    @app.route('/api/extensions/<ext_id>/permissions/escalation', methods=['POST'])
    def api_permissions_escalation(ext_id):
        """Grant or deny an escalation for an extension."""
        perm = get_permission_manager()
        data = request.get_json(silent=True) or {}
        method = data.get('method')
        grant = data.get('grant', False)
        once = data.get('once', False)

        if not method:
            return jsonify({'error': 'method is required'}), 400

        if grant:
            perm.grant_escalation(ext_id, method, once=once)
        else:
            perm.revoke_escalation(ext_id, method)

        return jsonify({'ok': True, 'method': method, 'granted': grant, 'once': once})

    @app.route('/api/extensions/<ext_id>/permissions/whitelist', methods=['POST'])
    def api_permissions_whitelist_add(ext_id):
        """Add a file to extension's whitelist (mediated access)."""
        perm = get_permission_manager()
        data = request.get_json(silent=True) or {}
        file_path = data.get('path')

        if not file_path:
            return jsonify({'error': 'path is required'}), 400

        perm.add_to_whitelist(ext_id, file_path)
        return jsonify({'ok': True})

    @app.route('/api/extensions/<ext_id>/permissions/whitelist', methods=['DELETE'])
    def api_permissions_whitelist_remove(ext_id):
        """Remove a file from extension's whitelist."""
        perm = get_permission_manager()
        data = request.get_json(silent=True) or {}
        file_path = data.get('path')

        if not file_path:
            return jsonify({'error': 'path is required'}), 400

        perm.remove_from_whitelist(ext_id, file_path)
        return jsonify({'ok': True})

    @app.route('/api/extensions/<ext_id>/permissions/whitelist')
    def api_permissions_whitelist_list(ext_id):
        """List whitelisted files for an extension."""
        perm = get_permission_manager()
        return jsonify({'whitelist': perm.get_whitelist(ext_id)})

    @app.route('/api/extensions/pending_consent')
    def api_pending_consent():
        """List all extensions pending consent."""
        from coreframe.extensions.loader import pending_consent, pending_migration
        perm = get_permission_manager()
        result = {}
        for ext_id, info in pending_consent.items():
            if perm.is_denied(ext_id):
                continue
            config = info.get('config', {})
            perm_info = perm.get_permission_info(config)
            result[ext_id] = {
                'id': ext_id,
                'name': info.get('name', ext_id),
                'level': info.get('level', 0),
                'permissions': perm_info,
                'type': 'consent',
            }
        for ext_id, info in pending_migration.items():
            config = info.get('config', {})
            result[ext_id] = {
                'id': ext_id,
                'name': info.get('name', ext_id),
                'level': -1,
                'permissions': {'level': -1, 'level_name': 'legacy'},
                'type': 'migration',
            }
        return jsonify(result)

    @app.route('/api/extensions/<ext_id>/migrate', methods=['POST'])
    def api_migrate_extension(ext_id):
        """Migrate a legacy extension with permissions."""
        from coreframe.extensions.loader import pending_migration, load_after_consent
        perm = get_permission_manager()

        data = request.get_json(silent=True) or {}
        level = data.get('level', 'basic')
        escalations = data.get('escalations', [])

        info = pending_migration.get(ext_id)
        if not info:
            return jsonify({'error': 'No pending migration for this extension'}), 404

        ext_path = info.get('path', os.path.join(EXTENSIONS_DIR, ext_id))
        config = info.get('config', {})

        if perm.migrate_extension(ext_path, config, level, escalations):
            # Now load the extension
            success = load_after_consent(ext_id)
            if success:
                return jsonify({'ok': True, 'loaded': True})
            else:
                return jsonify({'ok': True, 'loaded': False, 'message': 'Migration saved but load failed'})
        else:
            return jsonify({'error': 'Failed to write permissions to extension.json'}), 500

    @app.route('/api/extensions/<ext_id>/load', methods=['POST'])
    def api_extensions_load(ext_id):
        """Load a deferred hidden extension on demand."""
        from coreframe.extensions.loader import load_deferred, extensions as _exts
        if ext_id in _exts:
            return jsonify({'ok': True, 'loaded': True, 'already': True})
        ok = load_deferred(ext_id)
        return jsonify({'ok': ok, 'loaded': ok})

    @app.route('/api/extensions/<ext_id>/unload', methods=['POST'])
    def api_extensions_unload(ext_id):
        """Unload an extension and free its process (for hidden in all scenes)."""
        from coreframe.extensions.loader import extensions as _exts, _ext_isolation, _poll_stop_events
        ext_data = _exts.get(ext_id)
        if not ext_data:
            return jsonify({'ok': True, 'already': True})
        # Stop polling
        ev = _poll_stop_events.get(ext_id)
        if ev:
            ev.set()
        # Stop bridge process
        inst = ext_data.get('instance')
        if inst:
            try:
                if hasattr(inst, 'on_stop'):
                    inst.on_stop()
                elif hasattr(inst, 'stop'):
                    inst.stop()
            except Exception:
                pass
        _ext_isolation.mark_dead(ext_id, 'Unloaded (hidden in all scenes)')
        # Move to deferred for later reload via unhideWidget
        try:
            from coreframe.extensions.loader import _deferred_candidates
            from coreframe.config import EXTENSIONS_DIR
            import os
            # Keep path for reload
            cfg = ext_data.get('config', {})
            # Store for reload (use original ext_path if available)
            # We don't have ext_path here, but loader's _deferred_candidates expects it
            # So we keep a minimal entry: will be re-discovered via EXTENSIONS_DIR on next load
            # For now, just remove from extensions so it can be reloaded via load_deferred or load_after_consent
            pass
        except Exception:
            pass
        _exts.pop(ext_id, None)
        return jsonify({'ok': True, 'unloaded': True})

    # ── Existing routes ────────────────────────────────────────────

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
