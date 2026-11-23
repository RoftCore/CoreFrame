import os
import sys
import json
import shutil
import time
import threading

from coreframe.config import (
    log, EXTENSIONS_DIR, DATA_DATA_DIR, SHARED_LIB_DIR, REGISTRY_PATH
)
from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.deps import _ensure_extension_deps_async
from coreframe.extensions.permissions import get_permission_manager, PERMISSION_LEVELS, REQUIRES_CONSENT
from coreframe.extensions import state as ext_state

# State lives in runtime.py, pollers in polls.py; both re-exported here (pitfall 68).
from coreframe.extensions.runtime import (
    extensions, disabled_extensions, failed_extensions, pending_consent,
    pending_migration, denied_consent, _poll_stop_events, _poll_threads,
    _poll_last_emit, _poll_no_socket_logged, _poll_exit_reason, _poll_thread_event,
    _pending_scan_cache, _load_gate, LOAD_START_TIMEOUT, _ext_isolation,
)
from coreframe.extensions.polls import (
    widget_visible_anywhere, poller_running, resume_hidden_polls, pollers_status,
    stop_all_polls, start_polling as _start_polling,
    supervisor_loop as _poll_supervisor_loop,
)


def request_initial_load():
    """Open the load gate; called on every /api/extensions poll, so it must stay cheap."""
    _load_gate.set()


def wait_for_load_gate(timeout=LOAD_START_TIMEOUT):
    """True when the frontend asked (or the timeout fired), False on timeout."""
    return _load_gate.wait(timeout=timeout)


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
    """Permission gate: (ok, message, needs) before an extension is loaded."""
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
# Level bumped: re-ask consent at the new level instead of hard-denying.
            log.warning("Extension %s: consent level %d < required %d, re-asking",
                        ext_id, granted, level)
            pending_consent[ext_id] = {
                'name': config.get('name', ext_id),
                'config': config,
                'path': ext_path,
                'level': level,
                'previous_level': granted,
            }
            return False, 'needs_consent', {
                'name': config.get('name', ext_id),
                'level': level,
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

# ALL Python extensions run out of process; a level-0 declaration buys nothing.
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
    # One supervisor: visibility changes reach the backend through no endpoint.
    if not any(t.name == 'poll-supervisor' for t in threading.enumerate()):
        threading.Thread(target=_poll_supervisor_loop, daemon=True,
                         name='poll-supervisor').start()

    if not os.path.exists(EXTENSIONS_DIR):
        log.info("Extensions dir does not exist: %s", EXTENSIONS_DIR)
        return

    candidates = _scan_candidates()

    log.info("Found %d candidate extensions", len(candidates))

    for ext_id, ext_path in candidates:
        if is_disabled(ext_id):
# Registered but switched off: no process, no widget, and not a load failure.
            _remember_disabled(ext_id, ext_path)
            log.info("Extension %s is disabled, skipping", ext_id)
            continue

    for ext_id, ext_path in candidates:
        if ext_id in disabled_extensions:
            continue
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



def _scan_candidates():
    """Every extension directory load_extensions() will actually load, from one scan."""
    found = []
    try:
        names = sorted(os.listdir(EXTENSIONS_DIR))
    except OSError:
        return found
    for name in names:
        ext_path = os.path.join(EXTENSIONS_DIR, name)
        if not os.path.isdir(ext_path):
            continue
        config_path = os.path.join(ext_path, 'extension.json')
        main_path = os.path.join(ext_path, 'main.py')
        if os.path.exists(config_path) and os.path.exists(main_path):
            found.append((name, ext_path))
    return found


def unloadable_candidates():
    """Manifest directories that can never load, with the reason, so they stay visible."""
    out = []
    try:
        names = sorted(os.listdir(EXTENSIONS_DIR))
    except OSError:
        return out
    for name in names:
        ext_path = os.path.join(EXTENSIONS_DIR, name)
        if not os.path.isdir(ext_path):
            continue
        config_path = os.path.join(ext_path, 'extension.json')
        if not os.path.exists(config_path) or os.path.exists(os.path.join(ext_path, 'main.py')):
            continue
        try:
            with open(config_path, encoding='utf-8-sig') as f:
                cfg = json.load(f)
        except (OSError, ValueError) as e:
            out.append((name, {'id': name, 'name': name},
                        'Invalid extension.json: %s' % e))
            continue
        if not isinstance(cfg, dict):
            cfg = {'id': name, 'name': name}
        lang = cfg.get('language', 'python')
        main = cfg.get('main', 'main.py')
        out.append((cfg.get('id', name), cfg,
                    'No main.py: this is a %s extension (%s) and only Python '
                    'extensions load' % (lang, main)))
    return out


def pending_manifests():
    """Manifests installed but not loaded yet, so the host can hold the real grid slot."""
    if not _pending_scan_cache:
        for name, ext_path in _scan_candidates():
            cfg_path = os.path.join(ext_path, 'extension.json')
            try:
                with open(cfg_path, encoding='utf-8-sig') as f:
                    cfg = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(cfg, dict) and cfg.get('widgets'):
                _pending_scan_cache[cfg.get('id', name)] = cfg
    # Drop whatever has since loaded, failed or been disabled: only the outstanding remain.
    return {eid: cfg for eid, cfg in _pending_scan_cache.items()
            if eid not in extensions and eid not in failed_extensions
            and eid not in disabled_extensions and eid not in pending_consent
            and eid not in pending_migration and eid not in denied_consent}


def is_disabled(ext_id):
    # The flag lives in extensions.state.json, not in the generated registry (pitfall 47).
    return ext_state.is_disabled(ext_id)


def set_disabled(ext_id, flag):
    """Persist the disabled flag. Never touches the files on disk."""
    return ext_state.set_disabled(ext_id, flag)


def _remember_disabled(ext_id, ext_path):
    """Keep the manifest of a skipped extension so it can still be listed."""
    try:
        with open(os.path.join(ext_path, 'extension.json'), encoding='utf-8-sig') as f:
            disabled_extensions[ext_id] = {'config': json.load(f), 'path': ext_path}
    except (OSError, ValueError):
        disabled_extensions[ext_id] = {'config': {'id': ext_id, 'name': ext_id}, 'path': ext_path}


def unload_disabled(ext_id):
    """Stop a disabled extension that happens to be running."""
    from coreframe.extensions.loader import _poll_stop_events
    stop_evt = _poll_stop_events.pop(ext_id, None)
    if stop_evt:
        stop_evt.set()

    ext_data = extensions.pop(ext_id, None)
    # Keep the manifest so the sidebar can still switch it back on.
    if ext_data:
        disabled_extensions[ext_id] = {'config': ext_data.get('config', {'id': ext_id}),
                                       'path': ext_data.get('path')}
    inst = (ext_data or {}).get('instance')
    if inst is not None:
        # cleanup() first (it may want the child alive to flush), then on_stop() to kill it.
        for attr in ('cleanup', 'on_stop', 'stop'):
            fn = getattr(inst, attr, None)
            if not fn:
                continue
            try:
                fn()
            except Exception as e:
                log.warning("%s() failed for %s: %s", attr, ext_id, e)
            if attr == 'cleanup':
                continue      # on_stop() still has to run
    _ext_isolation.mark_dead(ext_id, 'Disabled')


def load_disabled(ext_id):
    """Bring a disabled extension back: clear the flag, then load it."""
    set_disabled(ext_id, False)
    disabled_extensions.pop(ext_id, None)
    return _load_single_extension(ext_id)


def _load_single_extension(ext_id):
    """Blocking load for dynamic installs."""
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    config_path = os.path.join(ext_path, 'extension.json')
    if not os.path.exists(config_path):
        return False
    if is_disabled(ext_id):
        _remember_disabled(ext_id, ext_path)
        log.info("Refusing to load %s: it is disabled", ext_id)
        return False

    def loader():
        success, error = _load_extension_core(ext_id, ext_path)
        if not success:
            if ext_id not in pending_consent and ext_id not in pending_migration and ext_id not in denied_consent:
                failed_extensions[ext_id] = {'name': ext_id, 'loadError': error}
                _ext_isolation.mark_dead(ext_id, error)
        return success

    # Carry the restart budget across; a fresh health would reset it to attempt 1.
    prior = _ext_isolation.health.get(ext_id)
    prior_restarts = prior.restart_count if prior else 0
    prior_quarantined = prior.quarantined if prior else False

    thread = _ext_isolation.start_load(ext_id, loader,
                                       restart_count=prior_restarts,
                                       quarantined=prior_quarantined)
    thread.join(timeout=15.0)
    return ext_id in extensions


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
    loaded = ext_id in extensions
    # A terminal event, or the install toast waits forever: this path runs after consent, when the install job has already emitted 'needs_consent' and returned.
    _si = getattr(_ext_isolation, '_socketio', None)
    if _si:
        if loaded:
            _si.emit('extension_install_progress', {'id': ext_id, 'step': 'done'})
        else:
            error = failed_extensions.get(ext_id, {}).get('loadError', 'Load failed after consent')
            _si.emit('extension_install_progress', {'id': ext_id, 'step': 'error', 'error': error})
    return loaded
