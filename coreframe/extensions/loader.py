import os
import sys
import json
import shutil
import importlib.util
import threading

from coreframe.config import (
    log, EXTENSIONS_DIR, DATA_DATA_DIR, SHARED_LIB_DIR
)
from coreframe.extensions.health import ExtensionIsolation
from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.deps import _ensure_extension_deps_async
from coreframe.extensions.permissions import get_permission_manager, PERMISSION_LEVELS, REQUIRES_CONSENT

# Global state — set by app.py
extensions = {}
failed_extensions = {}
pending_consent = {}  # Extensions waiting for user consent
pending_migration = {}  # Legacy extensions waiting for migration
denied_consent = {}  # Extensions whose consent was denied (store config for UI)
_deferred_candidates = {}  # Hidden extensions deferred for lazy load
_poll_stop_events = {}
_ext_isolation = ExtensionIsolation()


def _sync_extension_lib(ext_path):
    ext_lib = os.path.join(ext_path, 'lib')
    if os.path.isdir(ext_lib):
        for item in os.listdir(ext_lib):
            src = os.path.join(ext_lib, item)
            dst = os.path.join(SHARED_LIB_DIR, item)
            if not os.path.exists(dst):
                if os.path.isdir(src):
                    shutil.copytree(src, dst, ignore_dangling_symlinks=True)
                else:
                    shutil.copy2(src, dst)
                log.debug("Synced %s to shared lib", item)
        try:
            shutil.rmtree(ext_lib)
            log.debug("Removed shipped lib/ from %s", ext_path)
        except Exception:
            pass


def _check_permissions(ext_id: str, config: dict, ext_path: str) -> tuple:
    """
    Check extension permissions before loading.
    Returns: (can_load, status, detail)
        can_load: True if extension can be loaded
        status: 'ok' | 'needs_consent' | 'legacy' | 'denied'
        detail: additional info (error message, level info, etc.)
    """
    perm = get_permission_manager()
    level = perm.get_required_level(config)

    # Legacy: no permissions field
    if level == -1:
        log.warning("Extension %s has no permissions field (legacy)", ext_id)
        pending_migration[ext_id] = {
            'name': config.get('name', ext_id),
            'config': config,
            'path': ext_path,
        }
        return False, 'legacy', {
            'name': config.get('name', ext_id),
            'config': config,
        }

    # Low levels (0-2): no consent required
    if level < 3:
        return True, 'ok', {}

    # Levels 3-5: check consent
    if perm.has_consent(ext_id):
        granted = perm.get_granted_level(ext_id)
        if granted >= level:
            return True, 'ok', {}
        else:
            log.warning("Extension %s: consent level %d < required %d", ext_id, granted, level)
            return False, 'denied', {
                'reason': f'Consent level {granted} insufficient, need {level}',
            }

    # Check if previously denied
    if perm.is_denied(ext_id):
        log.info("Extension %s: consent previously denied", ext_id)
        denied_consent[ext_id] = {
            'name': config.get('name', ext_id),
            'config': config,
            'path': ext_path,
            'level': level,
        }
        return False, 'denied', {
            'name': config.get('name', ext_id),
            'level': level,
            'reason': 'Consent denied by user',
        }

    # No consent: needs it
    log.info("Extension %s needs consent at level %d", ext_id, level)
    pending_consent[ext_id] = {
        'name': config.get('name', ext_id),
        'config': config,
        'path': ext_path,
        'level': level,
    }
    return False, 'needs_consent', {
        'name': config.get('name', ext_id),
        'level': level,
    }


def _load_extension_core(ext_id: str, ext_path: str) -> tuple[bool, str]:
    """Core loading logic - returns (success, error_msg)."""
    config_path = os.path.join(ext_path, 'extension.json')
    main_path = os.path.join(ext_path, 'main.py')

    if not os.path.exists(config_path):
        return False, "No extension.json"
    if not os.path.exists(main_path):
        return False, "No main.py"

    try:
        with open(config_path, encoding='utf-8-sig') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"Invalid extension.json: {e}"
    except Exception as e:
        return False, f"Config read error: {e}"

    current_os = 'linux' if not sys.platform.startswith('win') else 'windows'
    platforms = config.get('platforms')
    if platforms is not None and current_os not in platforms:
        return False, f"Platform mismatch: {current_os} not in {platforms}"

    # ── Permission check ───────────────────────────────────────────
    can_load, status, detail = _check_permissions(ext_id, config, ext_path)
    if not can_load:
        if status == 'legacy':
            return False, f"Legacy extension - needs migration (no permissions defined)"
        elif status == 'needs_consent':
            # Emit consent request to frontend
            perm = get_permission_manager()
            perm.emit_needs_consent(
                ext_id,
                config.get('name', ext_id),
                detail.get('level', 0),
                config.get('permissions', {}),
            )
            return False, f"Needs user consent at level {detail.get('level', 0)}"
        elif status == 'denied':
            return False, detail.get('reason', 'Permission denied')
        return False, "Permission check failed"

    try:
        _sync_extension_lib(ext_path)
        _ensure_extension_deps_async(ext_path, ext_id)
        config['data_dir'] = os.path.join(DATA_DATA_DIR, ext_id)
        lang = config.get('language', 'python')

        # Subprocess isolation for ALL Python extensions.
        # A malicious extension could declare level 0 to bypass level-based
        # isolation, so ALL Python extensions go through SubprocessBridge + ext_runner.py.
        # OS-level restrictions are applied by ext_runner based on the declared level.
        perms = config.get('permissions', {})
        level_val = perms.get('level', 0)
        if isinstance(level_val, int):
            perm_level = level_val
        else:
            perm_level = {'basic': 0, 'storage': 1, 'user_files': 2,
                         'network': 3, 'system': 4, 'admin': 5}.get(str(level_val).lower(), 0)

        if lang != 'python' and lang != 'py':
            ext_instance = SubprocessBridge(config, ext_path, _ext_isolation)
        else:
            log.info("[Loader] Python extension %s (level %d) -> subprocess isolation", ext_id, perm_level)
            config['isolated'] = True
            ext_instance = SubprocessBridge(config, ext_path, _ext_isolation)

        extensions[ext_id] = {'config': config, 'instance': ext_instance}
        failed_extensions.pop(ext_id, None)

        _start_polling(ext_id, extensions[ext_id])

        return True, ""
    except Exception as e:
        mod_name = f"extensions.{ext_id}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        extensions.pop(ext_id, None)
        return False, str(e)


def load_extensions():
    """NON-BLOCKING: Starts async loading of all extensions."""
    log.info("load_extensions: Starting async load (EXTENSIONS_DIR=%s)", EXTENSIONS_DIR)
    _ext_isolation.start_monitor()

    if not os.path.exists(EXTENSIONS_DIR):
        log.info("Extensions dir does not exist: %s", EXTENSIONS_DIR)
        return

    candidates = []
    for name in os.listdir(EXTENSIONS_DIR):
        ext_path = os.path.join(EXTENSIONS_DIR, name)
        if not os.path.isdir(ext_path):
            continue
        config_path = os.path.join(ext_path, 'extension.json')
        main_path = os.path.join(ext_path, 'main.py')
        if os.path.exists(config_path) and os.path.exists(main_path):
            candidates.append((name, ext_path))

    log.info("Found %d candidate extensions", len(candidates))

    for ext_id, ext_path in candidates:
        def make_loader(eid, epath):
            def loader():
                success, error = _load_extension_core(eid, epath)
                if not success:
                    # Only mark as failed if not pending consent/migration/denied
                    if eid not in pending_consent and eid not in pending_migration and eid not in denied_consent:
                        failed_extensions[eid] = {'name': eid, 'loadError': error}
                        _ext_isolation.mark_dead(eid, error)
                    log.error("Extension %s failed: %s", eid, error)
                return success
            return loader

        _ext_isolation.start_load(ext_id, make_loader(ext_id, ext_path))

    # Protect consent files from being edited by in-process extensions
    from coreframe.extensions.security import protect_consent_files
    protect_consent_files()


def _load_single_extension(ext_id):
    """Blocking load for dynamic installs."""
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    config_path = os.path.join(ext_path, 'extension.json')
    if not os.path.exists(config_path):
        return False

    def loader():
        success, error = _load_extension_core(ext_id, ext_path)
        if not success:
            if ext_id not in pending_consent and ext_id not in pending_migration and ext_id not in denied_consent:
                failed_extensions[ext_id] = {'name': ext_id, 'loadError': error}
                _ext_isolation.mark_dead(ext_id, error)
        return success

    thread = _ext_isolation.start_load(ext_id, loader)
    thread.join(timeout=15.0)
    return ext_id in extensions


def _start_polling(ext_id, ext_data):
    """Start realtime polling for an extension if configured."""
    # Lazy import to avoid circular dependency
    from coreframe.websocket import _poll_extension
    cfg = ext_data['config']
    interval = cfg.get('refresh_interval', 0)
    if cfg.get('realtime', False) and interval > 0 and cfg.get('widgets', []):
        stop_event = threading.Event()
        _poll_stop_events[ext_id] = stop_event
        t = threading.Thread(target=_poll_extension, args=(ext_id, ext_data, interval), daemon=True)
        t.start()


# ── Consent migration helpers ──────────────────────────────────────

def load_after_consent(ext_id: str):
    """Load an extension after consent has been granted."""
    info = pending_consent.pop(ext_id, None)
    if not info:
        # Also check pending_migration
        info = pending_migration.pop(ext_id, None)
    if not info:
        # Also check denied (user may grant after denying)
        info = denied_consent.pop(ext_id, None)
    if not info:
        log.warning("load_after_consent: no pending entry for %s", ext_id)
        return False

    ext_path = info.get('path', os.path.join(EXTENSIONS_DIR, ext_id))

    def loader():
        success, error = _load_extension_core(ext_id, ext_path)
        if not success:
            failed_extensions[ext_id] = {'name': ext_id, 'loadError': error}
            _ext_isolation.mark_dead(ext_id, error)
            log.error("Extension %s failed after consent: %s", ext_id, error)
        return success

    thread = _ext_isolation.start_load(ext_id, loader)
    thread.join(timeout=15.0)
    return ext_id in extensions


def load_deferred(ext_id: str):
    """Load a deferred hidden extension on demand (lazy load)."""
    ext_path = _deferred_candidates.pop(ext_id, None)
    if not ext_path:
        return ext_id in extensions
    log.info("Lazy loading deferred extension %s", ext_id)
    def loader():
        success, error = _load_extension_core(ext_id, ext_path)
        if not success:
            if ext_id not in pending_consent and ext_id not in pending_migration and ext_id not in denied_consent:
                failed_extensions[ext_id] = {'name': ext_id, 'loadError': error}
                _ext_isolation.mark_dead(ext_id, error)
            log.error("Deferred extension %s failed: %s", ext_id, error)
        return success
    thread = _ext_isolation.start_load(ext_id, loader)
    thread.join(timeout=15.0)
    return ext_id in extensions
