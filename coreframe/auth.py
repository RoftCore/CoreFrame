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
AUTOSTART_MODES = ('off', 'on', 'minimized')
# The host reads these flags in run_coreframe.pyw: --autostart boots the window
# visible, --minimized leaves it hidden with only the tray icon. Minimized is
# the background-services mode: extensions load, nothing is shown.
_MODE_FLAG = {'on': '--autostart', 'minimized': '--minimized'}


def _parse_autostart_value(val):
    """'"C:\\path\\CoreFrame.exe" --minimized' -> 'minimized' ('off' if unusable)."""
    p = (val or '').strip()
    if p.startswith('"'):
        p = p[1:].split('"', 1)[0]
    else:
        p = p.split()[0] if p.split() else ''
    # isfile() on the whole string (quotes + args) is always False, so the exe
    # path has to be pulled out first. A stale path counts as off.
    if not p or not os.path.isfile(p):
        return 'off'
    low = (val or '').lower()
    for mode in ('minimized', 'on'):
        if _MODE_FLAG[mode] in low:
            return mode
    return 'on'


def _get_autostart_mode():
    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
            try:
                val, _ = winreg.QueryValueEx(key, AUTOSTART_KEY)
                winreg.CloseKey(key)
                return _parse_autostart_value(val)
            except FileNotFoundError:
                winreg.CloseKey(key)
                return 'off'
        elif sys.platform == 'linux':
            path = os.path.join(os.path.expanduser('~'), '.config', 'autostart', 'coreframe.desktop')
            if not os.path.isfile(path):
                return 'off'
            with open(path, encoding='utf-8') as f:
                return _parse_autostart_value(f.read().replace('Exec=', '').strip())
        return 'off'
    except Exception:
        return 'off'


def _set_autostart_mode(mode):
    mode = mode if mode in AUTOSTART_MODES else 'off'
    try:
        if sys.platform == 'win32':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE)
            if mode == 'off':
                try:
                    winreg.DeleteValue(key, AUTOSTART_KEY)
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, AUTOSTART_KEY, 0, winreg.REG_SZ,
                                  '"{}" {}'.format(sys.executable, _MODE_FLAG[mode]))
            winreg.CloseKey(key)
            return True
        elif sys.platform == 'linux':
            autostart_dir = os.path.join(os.path.expanduser('~'), '.config', 'autostart')
            path = os.path.join(autostart_dir, 'coreframe.desktop')
            if mode == 'off':
                if os.path.isfile(path):
                    os.remove(path)
            else:
                os.makedirs(autostart_dir, exist_ok=True)
                content = (
                    '[Desktop Entry]\n'
                    'Type=Application\n'
                    'Name=CoreFrame\n'
                    'Exec={} {}\n'
                    'Terminal=false\n'
                ).format(sys.executable, _MODE_FLAG[mode])
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
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
                return jsonify({'error': 'Not available', 'available': False, 'mode': 'off'}), 400
            data = request.get_json(silent=True) or {}
            mode = data.get('mode')
            if mode not in AUTOSTART_MODES:
                # No explicit mode: cycle, so a bare click still toggles.
                cur = _get_autostart_mode()
                mode = 'on' if cur == 'off' else ('minimized' if cur == 'on' else 'off')
            _set_autostart_mode(mode)
        mode = _get_autostart_mode()
        return jsonify({
            'mode': mode,
            'enabled': mode != 'off',
            'available': frozen
        })

    @app.before_request
    def check_token():
        if request.path.startswith('/api/') and request.path not in ('/api/token', '/api/health', '/api/debug', '/api/debug.js'):
            token = request.headers.get('X-CoreFrame-Token', '')
            if token != _LOCAL_TOKEN:
                return jsonify({'error': 'Unauthorized'}), 403
