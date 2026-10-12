import os
import time
from flask import request
from flask import jsonify
from coreframe.config import EXTENSIONS_DIR, REGISTRY_PATH, log
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.extensions.permissions import PERMISSION_LEVELS, PERMISSION_NAMES
from coreframe.extensions.permissions import get_permission_manager

def _ext_is_booting(ext_id):
    """True if the extension is on disk but has not registered yet.

    Extensions load asynchronously, so the frontend's first calls can land
    before the instance is in `extensions`. The extension is there, just not
    ready.
    """
    try:
        return os.path.isfile(os.path.join(EXTENSIONS_DIR, ext_id, 'main.py'))
    except Exception:
        return False



def register_actions_routes(app, socketio):
    """Register the actions API routes."""
    @app.route('/api/extension/<ext_id>/<action>', methods=['GET', 'POST'])
    def api_extension_action(ext_id, action):
        if ext_id not in extensions:
            # Not registered yet. If it exists on disk it is still booting, so
            # wait briefly for it instead of failing the caller's first attempt.
            if _ext_is_booting(ext_id):
                deadline = time.time() + 3.0
                while time.time() < deadline and ext_id not in extensions:
                    time.sleep(0.05)
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

