import os
import sys
import hashlib

from flask import request, jsonify

# These will be set by app.py after Flask init
_app = None
_LOCAL_TOKEN = None


def init_auth(app):
    global _app, _LOCAL_TOKEN
    _app = app
    _LOCAL_TOKEN = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
    return _LOCAL_TOKEN


def get_token():
    return _LOCAL_TOKEN


# ── Autostart ──────────────────────────────────────────────────────

AUTOSTART_KEY = 'CoreFrame'


def _get_autostart_enabled():
    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
            try:
                val, _ = winreg.QueryValueEx(key, AUTOSTART_KEY)
                winreg.CloseKey(key)
                return os.path.isfile(val)
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        elif sys.platform == 'linux':
            path = os.path.join(os.path.expanduser('~'), '.config', 'autostart', 'coreframe.desktop')
            return os.path.isfile(path)
        return False
    except Exception:
        return False


def _set_autostart_enabled(enable):
    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, AUTOSTART_KEY, 0, winreg.REG_SZ, f'"{sys.executable}" --autostart')
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_KEY)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        elif sys.platform == 'linux':
            autostart_dir = os.path.join(os.path.expanduser('~'), '.config', 'autostart')
            path = os.path.join(autostart_dir, 'coreframe.desktop')
            if enable:
                os.makedirs(autostart_dir, exist_ok=True)
                content = (
                    '[Desktop Entry]\n'
                    'Type=Application\n'
                    'Name=CoreFrame\n'
                    f'Exec={sys.executable} --autostart\n'
                    'Terminal=false\n'
                )
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                if os.path.isfile(path):
                    os.remove(path)
            return True
        return False
    except Exception:
        return False


def register_auth_routes(app):
    @app.route('/api/token')
    def api_token():
        return jsonify({'token': _LOCAL_TOKEN})

    @app.route('/api/autostart', methods=['GET', 'POST'])
    def api_autostart():
        frozen = getattr(sys, 'frozen', False)
        if request.method == 'POST':
            if not frozen:
                return jsonify({'error': 'Not available', 'available': False, 'enabled': False}), 400
            enabled = _get_autostart_enabled()
            _set_autostart_enabled(not enabled)
        return jsonify({
            'enabled': _get_autostart_enabled(),
            'available': frozen
        })

    @app.before_request
    def check_token():
        if request.path.startswith('/api/') and request.path not in ('/api/token', '/api/health', '/api/debug', '/api/debug.js'):
            token = request.headers.get('X-CoreFrame-Token', '')
            if token != _LOCAL_TOKEN:
                return jsonify({'error': 'Unauthorized'}), 403
