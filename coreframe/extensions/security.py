"""
CoreFrame Extension Security Enforcement Layer.

Ensures each extension operates only within its granted permission level.
Does NOT restrict what extensions CAN do — enforces what they're ALLOWED to do.
"""
import os
import sys
import json
import stat
import builtins
import threading
import functools
import logging
import traceback

log = logging.getLogger('CoreFrame.security')

# ── Protected Resources ───────────────────────────────────────────
# These files/dirs are NEVER writable by extensions, regardless of level.

_CONSENT_FILENAMES = {
    'permissions_consent.json',
    'permissions_denied.json',
    'file_whitelists.json',
}

# Thread-local storage for current extension context
_current_ext = threading.local()

# Original builtins (saved before any patching)
_original_builtins_open = builtins.open
_original_builtins_import = builtins.__import__

# Track which extensions have been patched
_patched_modules = {}


class ExtensionSecurity:
    """
    Per-extension security context. Enforces permission level on operations.

    Usage (in loader.py after creating ext_instance):
        sec = ExtensionSecurity(ext_id, ext_config, ext_instance)
        sec.apply()
    """

    def __init__(self, ext_id, config, instance):
        self.ext_id = ext_id
        self.config = config
        self.instance = instance
        self.data_dir = config.get('data_dir', '')
        self.level = self._extract_level(config)

        from coreframe.config import DATA_DIR, SHARED_LIB_DIR
        self.coreframe_data_dir = DATA_DIR
        self.shared_lib_dir = SHARED_LIB_DIR

    def _extract_level(self, config):
        """Extract numeric permission level from config."""
        perms = config.get('permissions', {})
        level_val = perms.get('level', 0)
        if isinstance(level_val, int):
            return level_val
        level_map = {'basic': 0, 'storage': 1, 'user_files': 2,
                     'network': 3, 'system': 4, 'admin': 5}
        return level_map.get(str(level_val).lower(), 0)

    def apply(self):
        """Apply security restrictions to the extension instance."""
        if self.level >= 5:
            return  # Admin: full access, no restrictions

        self._protect_consent_file()
        self._protect_shared_lib()
        self._wrap_file_operations()
        self._wrap_network_operations()
        self._wrap_subprocess_operations()
        self._patch_builtins()
        self._patch_os_module()
        self._patch_subprocess_module()
        log.info("[Security] Applied level %d restrictions to %s", self.level, self.ext_id)

    # ── Consent File Protection ────────────────────────────────────

    def _protect_consent_file(self):
        """Make consent files read-only so extension can't self-escalate."""
        from coreframe.config import DATA_DIR
        for fname in _CONSENT_FILENAMES:
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                try:
                    os.chmod(fpath, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                except Exception:
                    pass

    # ── Shared Lib Protection ──────────────────────────────────────

    def _protect_shared_lib(self):
        """
        Wrap the extension's _sync_extension_lib to prevent writing to shared dir.
        This is a defense-in-depth measure.
        """
        # We can't un-write files already synced, but we can prevent future writes
        # by making the shared lib dir read-only for new files.
        # This is handled at the API level instead.
        pass

    # ── File Operations ────────────────────────────────────────────

    def _wrap_file_operations(self):
        """
        Wrap the extension instance's methods that do file I/O.
        Intercepts write_file, edit_file, delete_file, list_dir, read_file.
        """
        if self.level >= 4:
            return  # System+ : unrestricted file access

        for method_name in ('write_file', 'edit_file', 'replace_file',
                            'delete_file', 'list_dir', 'read_file'):
            if hasattr(self.instance, method_name):
                original = getattr(self.instance, method_name)
                setattr(self.instance, method_name,
                        self._wrap_file_method(original, method_name))

    def _wrap_file_method(self, original, method_name):
        """Wrap a single file method with path validation."""
        security = self

        @functools.wraps(original)
        def wrapped(payload=None):
            payload = payload or {}
            path = payload.get('path', '')
            if path and not security._validate_file_path(path, method_name):
                return {"error": f"Access denied: {method_name} not allowed for level {security.level} on path {path}"}
            return original(payload)

        return wrapped

    def _validate_file_path(self, path, operation):
        """
        Validate a file path against the extension's permission level.

        Level 0 (basic): no file access
        Level 1 (storage): own data_dir only
        Level 2 (user_files): mediated — check whitelist or user selection
        Level 3 (network): read only (no write/delete)
        Level 4+ (system/admin): unrestricted
        """
        if self.level == 0:
            return False  # No file access at all

        if self.level == 1:
            # Storage: only own data_dir
            return self._is_under_dir(path, self.data_dir)

        if self.level == 2:
            # User files: mediated — check whitelist
            from coreframe.extensions.permissions import get_permission_manager
            perm = get_permission_manager()
            return perm.is_file_allowed(self.ext_id, path)

        if self.level == 3:
            # Network: read-only, no destructive operations
            return operation in ('read_file', 'list_dir')

        return True  # Level 4+: unrestricted

    def _is_under_dir(self, path, parent_dir):
        """Check if path is under the given parent directory."""
        try:
            path = os.path.normpath(os.path.abspath(path))
            parent = os.path.normpath(os.path.abspath(parent_dir))
            return path.startswith(parent + os.sep) or path == parent
        except Exception:
            return False

    # ── Network Operations ─────────────────────────────────────────

    def _wrap_network_operations(self):
        """
        Block network access for extensions below level 3.
        Wraps methods that might do HTTP requests.
        """
        if self.level >= 3:
            return  # Network+ : allowed

        # Extensions below level 3 shouldn't make network calls.
        # We can't easily block all network access for in-process Python,
        # but we can wrap known network-using methods.
        for method_name in ('fetch', 'download', 'upload', 'request',
                            'get', 'post', 'put', 'delete'):
            if hasattr(self.instance, method_name):
                original = getattr(self.instance, method_name)
                setattr(self.instance, method_name,
                        self._block_method(original, method_name, 'network'))

    # ── Subprocess Operations ──────────────────────────────────────

    def _wrap_subprocess_operations(self):
        """
        Block subprocess execution for extensions below level 4.
        """
        if self.level >= 4:
            return  # System+ : allowed

        for method_name in ('run', 'execute', 'system', 'shell', 'popen'):
            if hasattr(self.instance, method_name):
                original = getattr(self.instance, method_name)
                setattr(self.instance, method_name,
                        self._block_method(original, method_name, 'system'))

    def _block_method(self, original, method_name, category):
        """Block a method call with an error message."""
        security = self

        @functools.wraps(original)
        def blocked(payload=None):
            return {"error": f"Access denied: {category} operations not allowed for level {security.level}"}

        return blocked

    # ── Builtin Patching (Direct Call Interception) ─────────────────

    def _patch_builtins(self):
        """
        Patch builtins.open globally to intercept direct file calls.
        Uses stack inspection to only restrict calls from extension modules.
        """
        security = self
        mod_name = f"extensions.{self.ext_id}"

        def restricted_open(*args, **kwargs):
            # Walk the call stack to find if any caller is an extension
            for depth in range(1, 8):
                try:
                    frame = sys._getframe(depth)
                    caller = frame.f_globals.get('__name__', '')
                    if caller.startswith('extensions.') and caller != 'extensions':
                        # Found an extension in the call stack — validate path
                        path = args[0] if args else kwargs.get('file', '')
                        if path and not security._validate_file_path(str(path), 'open'):
                            raise PermissionError(
                                f"Security: level {security.level} cannot access {path}"
                            )
                        break
                except ValueError:
                    break
            return _original_builtins_open(*args, **kwargs)

        builtins.open = restricted_open
        _patched_modules[mod_name] = True
        log.info("[Security] Patched builtins.open globally for %s", mod_name)

    def _patch_os_module(self):
        """Patch os.system and os.popen to check caller level."""
        import os as _os
        security = self

        if self.level >= 4:
            return  # System+ : allowed

        _orig_system = _os.system
        _orig_popen = _os.popen

        def restricted_system(cmd):
            for depth in range(1, 8):
                try:
                    frame = sys._getframe(depth)
                    caller = frame.f_globals.get('__name__', '')
                    if caller.startswith('extensions.') and caller != 'extensions':
                        raise PermissionError(
                            f"Security: level {security.level} cannot run os.system()"
                        )
                except ValueError:
                    break
            return _orig_system(cmd)

        def restricted_popen(cmd, *args, **kwargs):
            for depth in range(1, 8):
                try:
                    frame = sys._getframe(depth)
                    caller = frame.f_globals.get('__name__', '')
                    if caller.startswith('extensions.') and caller != 'extensions':
                        raise PermissionError(
                            f"Security: level {security.level} cannot run os.popen()"
                        )
                except ValueError:
                    break
            return _orig_popen(cmd, *args, **kwargs)

        _os.system = restricted_system
        _os.popen = restricted_popen

    def _patch_subprocess_module(self):
        """Patch subprocess.run/Popen to check caller level."""
        import subprocess as _subprocess
        security = self

        if self.level >= 4:
            return  # System+ : allowed

        _orig_run = _subprocess.run
        _orig_popen = _subprocess.Popen

        def restricted_run(*args, **kwargs):
            for depth in range(1, 8):
                try:
                    frame = sys._getframe(depth)
                    caller = frame.f_globals.get('__name__', '')
                    if caller.startswith('extensions.') and caller != 'extensions':
                        raise PermissionError(
                            f"Security: level {security.level} cannot run subprocess"
                        )
                except ValueError:
                    break
            return _orig_run(*args, **kwargs)

        class RestrictedPopen(_orig_popen):
            """Popen subclass that checks caller level on instantiation. Must
            remain a real class so libraries that subclass subprocess.Popen
            at import time (e.g. yt_dlp) still import cleanly."""
            def __init__(self, *args, **kwargs):
                for depth in range(1, 8):
                    try:
                        frame = sys._getframe(depth)
                        caller = frame.f_globals.get('__name__', '')
                        if caller.startswith('extensions.') and caller != 'extensions':
                            raise PermissionError(
                                f"Security: level {security.level} cannot spawn subprocess"
                            )
                    except ValueError:
                        break
                super().__init__(*args, **kwargs)

        _subprocess.run = restricted_run
        _subprocess.Popen = RestrictedPopen


# ── Module-Level Functions ─────────────────────────────────────────

def apply_security(ext_id, config, instance):
    """Apply security restrictions to an extension instance. Returns the instance."""
    try:
        sec = ExtensionSecurity(ext_id, config, instance)
        sec.apply()
    except Exception as e:
        log.warning("[Security] Failed to apply security to %s: %s", ext_id, e)
    return instance


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


def validate_api_path(ext_id, path, operation):
    """
    Validate a file path for an extension at the API level.
    Called from api.py routes that do file operations.
    Returns (allowed: bool, error: str|None).
    """
    from coreframe.extensions import extensions
    from coreframe.extensions.permissions import get_permission_manager

    ext_data = extensions.get(ext_id)
    if not ext_data:
        return False, "Extension not found"

    config = ext_data.get('config', {})
    perms = config.get('permissions', {})
    level_val = perms.get('level', 0)
    if isinstance(level_val, int):
        level = level_val
    else:
        level_map = {'basic': 0, 'storage': 1, 'user_files': 2,
                     'network': 3, 'system': 4, 'admin': 5}
        level = level_map.get(str(level_val).lower(), 0)

    if level >= 4:
        return True, None  # System+: unrestricted

    data_dir = config.get('data_dir', '')

    if level == 0:
        return False, "Level 0: no file access"

    if level == 1:
        try:
            norm_path = os.path.normpath(os.path.abspath(path))
            norm_data = os.path.normpath(os.path.abspath(data_dir))
            if norm_path.startswith(norm_data + os.sep) or norm_path == norm_data:
                return True, None
        except Exception:
            pass
        return False, f"Level 1: only own data_dir ({data_dir})"

    if level == 2:
        perm = get_permission_manager()
        if perm.is_file_allowed(ext_id, path):
            return True, None
        return False, "Level 2: file not in whitelist"

    if level == 3:
        if operation in ('read_file', 'list_dir'):
            return True, None
        return False, "Level 3: read-only"

    return True, None
