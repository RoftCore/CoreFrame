from flask import request
from flask import jsonify
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.extensions.permissions import PERMISSION_LABELS, PERMISSION_DESCRIPTIONS
from coreframe.extensions.permissions import PERMISSION_LEVELS, PERMISSION_NAMES
from coreframe.extensions.permissions import get_permission_manager
from coreframe.config import EXTENSIONS_DIR, REGISTRY_PATH, log
import os


def register_permissions_routes(app, socketio):
    """Register the permissions API routes."""
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

    @app.route('/api/extensions/<ext_id>/disable', methods=['POST'])
    def api_disable_extension(ext_id):
        """Stop an extension without touching its files or its registry entry.

        Re-enabling is the mirror image: clear the flag and load it again.
        """
        from coreframe.extensions.loader import (is_disabled, set_disabled,
                                                 unload_disabled, load_disabled)
        ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
        if not os.path.isdir(ext_path):
            return jsonify({'error': 'Extension not installed'}), 404
        if is_disabled(ext_id):
            return jsonify({'ok': True, 'disabled': True, 'id': ext_id})
        if not set_disabled(ext_id, True):
            return jsonify({'error': 'Could not persist the disabled flag'}), 500
        unload_disabled(ext_id)
        log.info("Extension %s disabled (files kept)", ext_id)
        return jsonify({'ok': True, 'disabled': True, 'id': ext_id})

    @app.route('/api/extensions/<ext_id>/enable', methods=['POST'])
    def api_enable_extension(ext_id):
        from coreframe.extensions.loader import is_disabled, set_disabled, load_disabled
        ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
        if not os.path.isdir(ext_path):
            return jsonify({'error': 'Extension not installed'}), 404
        if not is_disabled(ext_id):
            return jsonify({'ok': True, 'disabled': False, 'id': ext_id})
        set_disabled(ext_id, False)
        ok = load_disabled(ext_id)
        log.info("Extension %s enabled (loaded=%s)", ext_id, ok)
        return jsonify({'ok': True, 'disabled': False, 'id': ext_id, 'loaded': bool(ok)})

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
        for ext_id, info in list(pending_consent.items()):
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
        for ext_id, info in list(pending_migration.items()):
            config = info.get('config', {})
            result[ext_id] = {
                'id': ext_id,
                'name': info.get('name', ext_id),
                'level': -1,
                'permissions': {'level': -1, 'level_name': 'legacy'},
                'type': 'migration',
            }
        return jsonify(result)

