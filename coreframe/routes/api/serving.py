from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.config import EXTENSIONS_DIR, REGISTRY_PATH, log
import os

def _ext_serves_data(ext_id):
    """An extension opts into having its data dir served by reading its own manifest."""
    import json
    cfg_path = os.path.join(EXTENSIONS_DIR, ext_id, 'extension.json')
    try:
        with open(cfg_path, encoding='utf-8-sig') as f:
            return bool(json.load(f).get('serve_data'))
    except Exception:
        return False



def register_serving_routes(app, socketio):
    """Register the serving API routes."""
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
            resp = send_from_directory(static_dir, path)
        except FileNotFoundError:
            return Response('', 204)
# Long-cache only content-stable media (timestamped images); JS/CSS/HTML must never cache.
        lp = path.lower().replace('\\', '/')
        if lp.startswith('thumbs/') or lp.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico')):
            resp.headers['Cache-Control'] = 'public, max-age=86400'
        else:
            resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp

    def _ext_serves_data(ext_id):
        """An extension opts into having its data dir served by reading its own manifest."""
        import json
        cfg_path = os.path.join(EXTENSIONS_DIR, ext_id, 'extension.json')
        try:
            with open(cfg_path, encoding='utf-8-sig') as f:
                return bool(json.load(f).get('serve_data'))
        except Exception:
            return False

    @app.route('/ext-data/<ext_id>/<path:path>')
    def ext_data(ext_id, path):
        """Serve an extension's own data dir (libraries, downloads).
        Requires "serve_data": true in the extension's own manifest, and
        conditional=True keeps HTTP Range (206) so <audio>/<video> can seek."""
        from flask import Response, send_from_directory
        from coreframe.config import DATA_DATA_DIR
        if '..' in ext_id or '/' in ext_id or '\\' in ext_id:
            return Response('Invalid extension id', 400)
        if not _ext_serves_data(ext_id):
            return Response('', 404)
        data_dir = os.path.join(DATA_DATA_DIR, ext_id)
        if not os.path.isdir(data_dir):
            return Response('', 204)
        try:
            return send_from_directory(data_dir, path, conditional=True)
        except FileNotFoundError:
            return Response('', 204)

