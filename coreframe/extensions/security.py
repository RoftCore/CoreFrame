"""Consent-file protection and API-level path validation.

Per-extension permission levels are enforced inside the child process
(ext_runner._apply_restrictions), not here: the host only guards the files
that record the user's own decisions.
"""
import logging
import os
import stat

log = logging.getLogger('CoreFrame.security')

# Never writable by extensions, whatever their level
_CONSENT_FILENAMES = {
    'permissions_consent.json',
    'permissions_denied.json',
    'file_whitelists.json',
}

_LEVELS = {'basic': 0, 'storage': 1, 'user_files': 2, 'network': 3, 'system': 4, 'admin': 5}


def protect_consent_files():
    """Make consent files read-only. Call at startup after loading extensions."""
    from coreframe.config import DATA_DIR
    for fname in _CONSENT_FILENAMES:
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.chmod(fpath, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            except Exception:
                pass


def restore_consent_files():
    """Restore consent files to writable. Only call during consent grant/deny API."""
    from coreframe.config import DATA_DIR
    for fname in _CONSENT_FILENAMES:
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.chmod(fpath, stat.S_IWRITE | stat.S_IRUSR)
            except Exception:
                pass


def _level_of(config):
    raw = (config.get('permissions') or {}).get('level', 0)
    if isinstance(raw, int):
        return raw
    return _LEVELS.get(str(raw).lower(), 0)


def validate_api_path(ext_id, path, operation):
    """Check a file path against the extension level. Returns (allowed, error)."""
    from coreframe.extensions import extensions
    from coreframe.extensions.permissions import get_permission_manager

    ext_data = extensions.get(ext_id)
    if not ext_data:
        return False, "Extension not found"

    config = ext_data.get('config', {})
    level = _level_of(config)
    if level >= 4:
        return True, None

    if level == 0:
        return False, "Level 0: no file access"

    if level == 1:
        data_dir = config.get('data_dir', '')
        try:
            norm_path = os.path.normpath(os.path.abspath(path))
            norm_data = os.path.normpath(os.path.abspath(data_dir))
            if norm_path.startswith(norm_data + os.sep) or norm_path == norm_data:
                return True, None
        except Exception:
            pass
        return False, f"Level 1: only own data_dir ({data_dir})"

    if level == 2:
        if get_permission_manager().is_file_allowed(ext_id, path):
            return True, None
        return False, "Level 2: file not in whitelist"

    if level == 3:
        if operation in ('read_file', 'list_dir'):
            return True, None
        return False, "Level 3: read-only"

    return True, None
