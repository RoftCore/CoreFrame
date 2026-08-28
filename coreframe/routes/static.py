import sys
from flask import Response, send_from_directory

from coreframe.config import STATIC_DIR


def register_static_routes(app):

    @app.route('/api/debug.js')
    def api_debug_js():
        frozen = getattr(sys, 'frozen', False)
        debug_status = 'false' if frozen else 'true'
        return Response(f'const _COREFRAME_DEBUG = {debug_status};', mimetype='application/javascript')

    @app.route('/')
    def index():
        resp = send_from_directory(STATIC_DIR, 'index.html')
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp

    @app.route('/<path:path>')
    def static_files(path):
        resp = send_from_directory(STATIC_DIR, path)
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp
