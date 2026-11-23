"""Marketplace install machinery: replace a version on disk and roll back safely.

Split from marketplace.py by concern: these are the filesystem and version
operations, with no HTTP routes.
"""
import os
import shutil
import time

from coreframe.config import log, DATA_DIR, REGISTRY_PATH
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.extensions.loader import _load_single_extension, _sync_extension_lib
from coreframe.extensions.deps import _ensure_extension_deps_sync

# A backup inside EXTENSIONS_DIR would be discovered as an extension by _scan_candidates.
BACKUP_DIR = os.path.join(DATA_DIR, '.ext_backup')


def _stop_for_replace(ext_id):
    """Stop the poller and the child process before its files change."""
    from coreframe.extensions.loader import extensions as _exts, _poll_stop_events
    stop_event = _poll_stop_events.get(ext_id)
    if stop_event:
        stop_event.set()
    ext_data = _exts.get(ext_id)
    if ext_data:
        instance = ext_data.get('instance')
        if instance:
            try:
                if hasattr(instance, 'on_stop'):
                    instance.on_stop()
                elif hasattr(instance, 'stop'):
                    instance.stop()
            except Exception:
                pass
    _ext_isolation.mark_dead(ext_id, 'Unloaded for version change')
    _exts.pop(ext_id, None)
    failed_extensions.pop(ext_id, None)


def _kill_locks(target, ext_id):
    """Kill bridge runners whose cwd is inside the target, or Windows will not rename it."""
    try:
        import psutil
        from coreframe.extensions.bridge import SubprocessBridge
    except Exception:
        return 0
    killed = 0
    root = os.path.normcase(os.path.abspath(target))
    with SubprocessBridge._live_lock:
        procs = list(SubprocessBridge._live_children)
    for proc in procs:
        try:
            if proc.poll() is not None:
                continue
            cwd = os.path.normcase(os.path.abspath(psutil.Process(proc.pid).cwd()))
        except Exception:
            continue
        if cwd == root or cwd.startswith(root + os.sep):
            try:
                proc.kill()
                proc.wait(timeout=3)
                killed += 1
                log.info("Killed runner pid=%d locking %s", proc.pid, ext_id)
            except Exception:
                pass
    return killed


def _backup_target(ext_id):
    """A free slot under BACKUP_DIR; never inside EXTENSIONS_DIR."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, ext_id)
    shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        path = os.path.join(BACKUP_DIR, f"{ext_id}-{int(time.time())}")
    return path


def _restore_backup(target, backup, ext_id=None):
    """Put the previous version back after a failed replace, then reload it."""
    if not backup or not os.path.isdir(backup):
        return False
    for _ in range(3):
        try:
            shutil.rmtree(target)
            break
        except OSError:
            time.sleep(0.5)
    if os.path.isdir(target):
        trash = os.path.join(BACKUP_DIR, f"{ext_id or 'ext'}-{int(time.time())}.failed")
        shutil.rmtree(trash, ignore_errors=True)
        try:
            os.replace(target, trash)
        except OSError as e:
            log.error("Could not move failed install aside (%s): %s", target, e)
            return False
    try:
        os.replace(backup, target)
        return True
    except OSError as e:
        log.error("Restore failed for %s: %s", target, e)
        return False


def _record_version(ext_id, ext_name, version):
    """Keep extensions.json in step with the manifest after a version change."""
    try:
        from coreframe.extensions import state as ext_state
        data = ext_state.read_json(REGISTRY_PATH)
        entry = data.get(ext_id) or {'name': ext_name, 'author': '', 'category': 'general'}
        if not isinstance(entry, dict):
            entry = {'name': ext_name, 'author': '', 'category': 'general'}
        if entry.get('version') == version:
            return
        entry['version'] = version
        entry.setdefault('name', ext_name)
        # A version switch is not an enable: whatever the user decided stands.
        entry['disabled'] = ext_state.is_disabled(ext_id)
        data[ext_id] = entry
        if not ext_state.write_json(REGISTRY_PATH, data):
            log.warning("Could not record version for %s", ext_id)
    except Exception as e:
        log.warning("Could not record version for %s: %s", ext_id, e)


def _bg_install_mkt(ext_id, target, ext_name, version, backup, socketio):
    """Files are already extracted: deps, load, and roll back to backup on failure."""
    def _fail(reason):
        log.error("Install of %s %s failed: %s", ext_id, version, reason)
        restored = _restore_backup(target, backup, ext_id)
        if not restored:
            try:
                from coreframe.routes.install import _rollback_install
                _rollback_install(ext_id, target)
            except Exception as e:
                log.error("Rollback failed for %s: %s", ext_id, e)
        failed_extensions.pop(ext_id, None)
        if restored:
            # The files are back but nothing loaded them: a failed update must not leave a dead extension.
            try:
                if _load_single_extension(ext_id):
                    ext_data = extensions.get(ext_id)
                    if ext_data:
                        from coreframe.extensions.loader import _start_polling
                        _start_polling(ext_id, ext_data)
                    log.info("Rolled back %s to the previous version", ext_id)
                else:
                    log.error("Rolled back files for %s but it did not load again", ext_id)
            except Exception as e:
                log.error("Reload after rollback failed for %s: %s", ext_id, e)
        socketio.emit('extension_install_progress',
                      {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': reason})

    try:
        socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'syncing'})
        _sync_extension_lib(target)
        socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'deps'})
        # Synchronous: loading before pip finishes is how console died on winpty.
        deps_ok, deps_err = _ensure_extension_deps_sync(target, ext_id)
        if not deps_ok:
            log.error("Marketplace deps failed for %s: %s", ext_id, deps_err)
            _fail(f"Failed to install dependencies: {deps_err}")
            return
        socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'loading'})
        if not _load_single_extension(ext_id):
            # Legacy or level-bump refusals are prompts, not failures (pitfall 48).
            from coreframe.extensions.loader import (
                pending_consent, pending_migration, denied_consent)
            if ext_id in pending_migration or ext_id in pending_consent:
                _record_version(ext_id, ext_name, version)
                if backup:
                    shutil.rmtree(backup, ignore_errors=True)
                legacy = ext_id in pending_migration
                level = (pending_consent.get(ext_id) or {}).get('level', 3)
                socketio.emit('extension_install_progress',
                              {'id': ext_id, 'name': ext_name,
                               'step': 'needs_migration' if legacy else 'needs_consent',
                               'level': level, 'version': version})
                log.info("Install of %s %s waits for %s", ext_id, version,
                         'migration' if legacy else 'consent')
                return
            if ext_id in denied_consent:
                _fail('Consent was denied for this extension: grant it in Settings > Extensions')
                return
            _fail(str(failed_extensions.get(ext_id, {}).get('loadError')
                      or 'The extension did not load (see Settings > Extensions for details)'))
            return
        ext_data = extensions.get(ext_id)
        if ext_data:
            from coreframe.extensions.loader import _start_polling
            _start_polling(ext_id, ext_data)
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
        _record_version(ext_id, ext_name, version)
        socketio.emit('extension_install_progress',
                      {'id': ext_id, 'name': ext_name, 'step': 'done', 'version': version})
    except Exception as e:
        log.error("Background install failed for %s: %s", ext_id, e)
        _fail(str(e))
