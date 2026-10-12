from flask import request
from flask import jsonify
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.config import EXTENSIONS_DIR, REGISTRY_PATH, log
import os
import sys


def register_debug_routes(app, socketio):
    """Register the debug API routes."""
    @app.route('/api/debug/switch', methods=['POST'])
    def api_debug_switch():
        """Receives scene-switch timing telemetry from the frontend.
        Lets us attribute slow switches (commit vs paint) without DevTools."""
        try:
            from coreframe.config import log as _log
            data = request.get_json(silent=True) or {}
            _log.info("[SwitchTelemetry] scene=%s commit_ms=%s paint_ms=%s phases=%s",
                      data.get('scene'), data.get('commit_ms'),
                      data.get('paint_ms'), data.get('phases'))
        except Exception:
            pass
        return jsonify({'ok': True})

    @app.route('/api/debug/longtask', methods=['POST'])
    def api_debug_longtask():
        """Receives main-thread freeze attribution from the frontend
        longtask observer (script URL + duration)."""
        try:
            from coreframe.config import log as _log
            data = request.get_json(silent=True) or {}
            for t in (data.get('tasks') or [])[:10]:
                _log.warning("[Freeze] main-thread blocked %sms by %s",
                             t.get('d'), t.get('src') or '?')
        except Exception:
            pass
        return jsonify({'ok': True})

    @app.route('/api/debug/console', methods=['POST'])
    def api_debug_console():
        """Console errors and warnings from the page.

        Extension JS runs inside the webview, so a throw in its boot script has
        no other way out: the card simply never renders and the host logs
        nothing. The remote-debugging port is ignored when the host runs
        elevated, so the page posts its own errors here.
        """
        try:
            from coreframe.config import log as _log
            data = request.get_json(silent=True) or {}
            for e in (data.get('entries') or [])[:30]:
                _log.warning("[PageJS] %s: %s | %s",
                             e.get('k'), e.get('m'), (e.get('s') or '')[-140:])
        except Exception:
            pass
        return jsonify({'ok': True})

    @app.route('/api/debug/drag', methods=['POST'])
    def api_debug_drag():
        """Geometry dump from the widget drag path (grid tracks, pitch, kids).
        Lets us check what the browser actually resolved instead of guessing."""
        try:
            from coreframe.config import log as _log
            d = request.get_json(silent=True) or {}
            _log.info("[DragGeometry] %s scene=%s rows=%s cols=%s rect=%s "
                      "inline_rows=%s used_rows=%r used_cols=%r auto_rows=%r flow=%r "
                      "px_rows=%s px_cols=%s derived_row0=%s pitch=%s kids=%s",
                      d.get('tag'), d.get('scene'), d.get('sceneRows'),
                      d.get('sceneCols'), d.get('rect'), d.get('inlineRows'),
                      d.get('rows'), d.get('cols'), d.get('autoRows'),
                      d.get('autoFlow'), d.get('pxRows'), d.get('pxCols'),
                      d.get('derivedRow0'), d.get('pitch'), d.get('kids'))
        except Exception:
            pass
        return jsonify({'ok': True})

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
