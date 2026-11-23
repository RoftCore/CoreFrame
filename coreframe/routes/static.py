import os
import sys
import time
from flask import Response, send_from_directory

from coreframe.config import STATIC_DIR

# One token per boot: index.html marks assets __CF_ASSET_V, so nobody bumps ?v= by hand.
_ASSET_V = str(int(time.time()))


def register_static_routes(app):

    @app.route('/api/debug.js')
    def api_debug_js():
        frozen = getattr(sys, 'frozen', False)
        debug_status = 'false' if frozen else 'true'
        return Response(f'const _COREFRAME_DEBUG = {debug_status};', mimetype='application/javascript')

    @app.route('/')
    def index():
        with open(os.path.join(STATIC_DIR, 'index.html'), encoding='utf-8') as f:
            html = f.read().replace('__CF_ASSET_V', _ASSET_V)
        resp = Response(html, mimetype='text/html')
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp

    @app.route('/<path:path>')
    def static_files(path):
        resp = send_from_directory(STATIC_DIR, path)
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp
