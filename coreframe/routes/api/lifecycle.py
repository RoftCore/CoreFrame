from flask import request
from flask import jsonify
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.extensions.permissions import get_permission_manager
from coreframe.config import EXTENSIONS_DIR, REGISTRY_PATH, log
import os


def register_lifecycle_routes(app, socketio):
    """Register the lifecycle API routes."""
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
        """Re-check a hidden extension: it is already loaded unless it failed."""
        from coreframe.extensions.loader import extensions as _exts, failed_extensions as _failed
        if ext_id in _exts:
            return jsonify({'ok': True, 'loaded': True, 'already': True})
        return jsonify({'ok': False, 'loaded': False,
                        'loadError': _failed.get(ext_id, {}).get('loadError', 'Not loaded')})

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

