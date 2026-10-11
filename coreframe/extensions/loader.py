import os
import sys
import json
import shutil
import time
import importlib.util
import threading

from coreframe.config import (
    log, EXTENSIONS_DIR, DATA_DATA_DIR, SHARED_LIB_DIR, REGISTRY_PATH
)
from coreframe.extensions.health import ExtensionIsolation
from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.deps import _ensure_extension_deps_async
from coreframe.extensions.permissions import get_permission_manager, PERMISSION_LEVELS, REQUIRES_CONSENT

# Global state — set by app.py
extensions = {}
# Disabled extensions: on disk and in the registry, but not loaded. Kept apart
# from failed_extensions because nothing is wrong with them.
disabled_extensions = {}
failed_extensions = {}
pending_consent = {}  # Extensions waiting for user consent
pending_migration = {}  # Legacy extensions waiting for migration
denied_consent = {}  # Extensions whose consent was denied (store config for UI)
_poll_stop_events = {}
# Poller threads and last emit time: the only way to tell a dead poller from a lost event.
_poll_threads = {}
_poll_last_emit = {}
# One-shot marker so a dead transport logs once, not every tick.
_poll_no_socket_logged = {}
# Stop reason and owning stop event: the supervisor resumes only hidden exits.
_poll_exit_reason = {}
_poll_thread_event = {}
# Manifests read once from disk to reserve grid space; see pending_manifests().
_pending_scan_cache = {}
# The load waits for the frontend to ask for the list so it can reserve the grid; the timeout covers minimized mode.
_load_gate = threading.Event()
LOAD_START_TIMEOUT = 8.0
_ext_isolation = ExtensionIsolation()


def request_initial_load():
    """Open the gate for the initial extension load. Idempotent and cheap.

    Called from /api/extensions on every poll, so it must do nothing after the
    first time.
    """
    _load_gate.set()


def wait_for_load_gate(timeout=LOAD_START_TIMEOUT):
    """True when the frontend asked (or the timeout fired), False on timeout."""
    return _load_gate.wait(timeout=timeout)


def widget_visible_anywhere(ext_id):
    """True when the widget is not hidden in at least one scene.

    Single source of truth: the poller used to carry its own copy of this and
    the supervisor needs the same answer, and two copies of a visibility rule
    always drift.
    """
    try:
        import json as _json
        from coreframe.config import WIDGET_STATE_PATH
        if not os.path.exists(WIDGET_STATE_PATH):
            return True
        with open(WIDGET_STATE_PATH, encoding='utf-8') as f:
            ws = _json.load(f)
        for sc in ws.get('scenes', {}).values():
            w = (sc.get('widgets') or {}).get(ext_id)
            if w and not w.get('hidden'):
                return True
        return False
    except Exception:
        return True


def _exited_while_hidden(ext_id):
    """True when this poller stopped because its widget was hidden everywhere.

    Prefix match: the reason is written as 'hidden in every scene', and an exact
    test against a shorter string never matches, leaving the widget frozen.
    """
    reason = _poll_exit_reason.get(ext_id) or ''
    return reason.startswith('hidden')


def poller_running(ext_id):
    """True only when the tracked thread is alive AND owns the current stop event.

    A replaced thread stays alive for a moment, so is_alive() alone reports a
    healthy poller for an extension that has none.
    """
    th = _poll_threads.get(ext_id)
    if not (th and th.is_alive()):
        return False
    return _poll_thread_event.get(ext_id) is _poll_stop_events.get(ext_id)


def resume_hidden_polls():
    """Restart realtime pollers whose widget is visible again but whose poller
    stopped while hidden.

    Without this, switching to a scene where the widget is hidden killed the
    poller for good and switching back left the widget frozen until CoreFrame
    was reloaded.
    """
    resumed = []
    for ext_id, ext_data in list(extensions.items()):
        cfg = ext_data.get('config') or {}
        if not cfg.get('realtime'):
            continue
        interval = cfg.get('refresh_interval', 0)
        if not interval or not cfg.get('widgets'):
            continue
        if not _exited_while_hidden(ext_id):
            continue
        if poller_running(ext_id):
            continue
        if not widget_visible_anywhere(ext_id):
            continue
        _start_polling(ext_id, ext_data)
        resumed.append(ext_id)
    if resumed:
        log.info("Resumed realtime polling for %s (widget visible again)",
                 ', '.join(resumed))
    return resumed


def _poll_supervisor_loop():
    """Watches for pollers that stopped while hidden and resumes them.

    Scene switches, unhiding and adding a widget to a scene all change
    visibility without telling the backend, so recovery cannot hang off a
    frontend callback.
    """
    while True:
        time.sleep(2.0)
        try:
            resume_hidden_polls()
        except Exception as e:
            log.debug("poll supervisor: %s", e)


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
            # Insufficient level (e.g. extension bumped 3 -> 4): re-ask
            # consent at the new level instead of hard-denying, otherwise
            # the modal never appears and the user can't grant it.
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


def pollers_status():
    """Per-extension poller liveness, for /api/debug/pollers.

    alive=false means the thread is gone and nothing restarts it, which is
    the one failure mode that silently kills a widget for the session.
    """
    import time as _t
    now = _t.time()
    from coreframe.websocket import latest_update
# Transport truth: a poller can be alive and updating the cache while the emit goes nowhere.
# The bound server lives on the isolation object; there is no module-level `si` here,
# which made this endpoint raise NameError on every call and 500 unconditionally.
    _si = getattr(_ext_isolation, '_socketio', None)
    transport = {
        'socketio_bound': _si is not None,
        'socketio_type': type(_si).__name__ if _si is not None else None,
    }
    out = {}
    for ext_id, ev in list(_poll_stop_events.items()):
        src = extensions.get(ext_id)
        if not src:
            src = disabled_extensions.get(ext_id) or {}
        cfg = src.get('config') or {}
        th = _poll_threads.get(ext_id)
        last = _poll_last_emit.get(ext_id)
        entry = {
            'alive': bool(th and th.is_alive()),
            'realtime': bool(cfg.get('realtime')),
            'interval': cfg.get('refresh_interval', 0),
            'widgets': len(cfg.get('widgets', []) or []),
            'has_values': ext_id in latest_update,
            'seconds_since_emit': round(now - last, 1) if last else None,
            'exit_reason': _poll_exit_reason.get(ext_id),
            'visible': widget_visible_anywhere(ext_id),
        }
        entry.update(transport)
        out[ext_id] = entry
    return out


def stop_all_polls(timeout=3.0):
    """Signal every realtime poll thread to exit and wait briefly.
    Must be called before any full reload so orphan pollers cannot pile up."""
    evs = list(_poll_stop_events.items())
    for _, ev in evs:
        try:
            ev.set()
        except Exception:
            pass
    _poll_stop_events.clear()
    _poll_threads.clear()
    # Clear reasons so a restart does not resume pollers for extensions it is replacing.
    _poll_thread_event.clear()
    _poll_exit_reason.clear()


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

    registry = _read_registry()
    for ext_id, ext_path in candidates:
        if registry.get(ext_id, {}).get('disabled'):
            # Installed and registered, but switched off. No process, no widget,
            # no polling, and it does not count as a load failure.
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
    """Every extension directory load_extensions() will actually load.

    One scan, one rule: a looser test here promised loads that never happen and
    left a placeholder card on the dashboard forever (a Node extension has no
    main.py).
    """
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


def pending_manifests():
    """Manifests of extensions installed but not loaded yet.

    Lets the host reserve the real grid slot while an extension is still
    loading; anything load_extensions() will never load is excluded, because a
    placeholder nothing replaces is worse than no placeholder.
    """
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
    # Drop whatever has since loaded, failed, been disabled or asked consent:
    # the caller only wants what is still outstanding.
    return {eid: cfg for eid, cfg in _pending_scan_cache.items()
            if eid not in extensions and eid not in failed_extensions
            and eid not in disabled_extensions and eid not in pending_consent
            and eid not in pending_migration and eid not in denied_consent}


def _read_registry():
    try:
        with open(REGISTRY_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def is_disabled(ext_id):
    return bool(_read_registry().get(ext_id, {}).get('disabled'))


def set_disabled(ext_id, flag):
    """Persist the disabled flag, creating the entry if the extension is not
    installed yet. Never touches the files on disk."""
    data = _read_registry()
    entry = data.get(ext_id)
    if not isinstance(entry, dict):
        entry = {'name': ext_id, 'version': '1.0', 'author': '', 'category': 'general'}
    entry['disabled'] = bool(flag)
    data[ext_id] = entry
    try:
        with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        log.error("Could not write disabled flag for %s: %s", ext_id, e)
        return False
    return True


def _remember_disabled(ext_id, ext_path):
    """Keep the manifest of a skipped extension so it can still be listed."""
    try:
        with open(os.path.join(ext_path, 'extension.json'), encoding='utf-8-sig') as f:
            disabled_extensions[ext_id] = {'config': json.load(f), 'path': ext_path}
    except (OSError, ValueError):
        disabled_extensions[ext_id] = {'config': {'id': ext_id, 'name': ext_id}, 'path': ext_path}


def unload_disabled(ext_id):
    """Stop a disabled extension that happens to be running.

    Same order as the delete path (see routes/install.py): stop the poller and
    the child BEFORE anything else, otherwise the isolation monitor keeps
    heartbeating and restarting something that is supposed to be off.
    """
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


def _start_polling(ext_id, ext_data):
    """Start realtime polling for an extension if configured."""
    # Lazy import to avoid circular dependency
    from coreframe.websocket import _poll_extension
    cfg = ext_data['config']
    interval = cfg.get('refresh_interval', 0)
    if cfg.get('realtime', False) and interval > 0 and cfg.get('widgets', []):
        stop_event = threading.Event()
        _poll_stop_events[ext_id] = stop_event
        t = threading.Thread(target=_poll_extension, args=(ext_id, ext_data, interval),
                             name="poll-%s" % ext_id, daemon=True)
        _poll_threads[ext_id] = t
        _poll_thread_event[ext_id] = stop_event
        _poll_exit_reason.pop(ext_id, None)
        _poll_last_emit.pop(ext_id, None)
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
