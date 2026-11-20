import io
import os
import json
import time
import shutil
import zipfile
import urllib.request
import threading
from flask import request, jsonify

from coreframe.config import log, EXTENSIONS_DIR, DATA_DIR, REGISTRY_PATH, MARKETPLACE_URL, PROVIDERS_PATH
from coreframe.utils import _is_safe_url
from coreframe.extensions import extensions, failed_extensions, _ext_isolation
from coreframe.extensions.loader import _load_single_extension, _sync_extension_lib
from coreframe.extensions.deps import _ensure_extension_deps_async, _ensure_extension_deps_sync

MARKETPLACE_CACHE = None
MARKETPLACE_CACHE_TIME = 0

# Previous version parked outside EXTENSIONS_DIR: a backup left inside it would
# be discovered as an extension by _scan_candidates (it has extension.json + main.py).
BACKUP_DIR = os.path.join(DATA_DIR, '.ext_backup')


def _ext_versions(ext_info):
    """Published versions newest-first; falls back to the flat version/URL pair."""
    versions = []
    for item in ext_info.get('versions') or []:
        version = str(item.get('version') or '').strip()
        url = item.get('download_url') or ''
        if version and url:
            versions.append((version, url))
    if not versions and ext_info.get('download_url'):
        versions.append((str(ext_info.get('version') or '1.0'), ext_info['download_url']))
    return versions


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
    """Kill bridge runners whose cwd is inside target.

    A load_extensions() racing with an install leaves an orphan runner whose cwd
    is the extension dir, and Windows refuses to rename a directory in that
    state (WinError 32). The tracked instance is already stopped; this catches
    the orphans nobody owns any more.
    """
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
    """Put the previous version back after a failed replace.

    A runner may still hold files inside target and Windows refuses to delete
    those, so move the directory aside instead of fighting the lock and rename
    the backup into place.
    """
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
            # The files are back but nothing loaded them: without this the user is
            # left with a dead extension after a failed update.
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
            # A refusal to load is not always a broken build. A legacy manifest
            # (published before the permissions field existed) or a level bump
            # parks the extension in pending_* waiting for the user. Rolling the
            # files back there would silently undo the version switch the user
            # just asked for, which is exactly how a downgrade "installed" and
            # still reported 1.1.
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


def _load_providers():
    try:
        with open(PROVIDERS_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_providers(providers):
    with open(PROVIDERS_PATH, 'w', encoding='utf-8') as f:
        json.dump(providers, f, indent=2)


def register_marketplace_routes(app, socketio):

    @app.route('/api/marketplace/list')
    def api_marketplace_list():
        global MARKETPLACE_CACHE, MARKETPLACE_CACHE_TIME
        now = time.time()
        if MARKETPLACE_CACHE and now - MARKETPLACE_CACHE_TIME < 120:
            return jsonify(MARKETPLACE_CACHE)
        try:
            req = urllib.request.Request(MARKETPLACE_URL)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            MARKETPLACE_CACHE = data
            MARKETPLACE_CACHE_TIME = now
            return jsonify(data)
        except Exception as e:
            log.error("Marketplace fetch failed: %s", e)
            return jsonify({'error': str(e)}), 502

    @app.route('/api/marketplace/install/<ext_id>', methods=['POST'])
    def api_marketplace_install(ext_id):
        try:
            req = urllib.request.Request(MARKETPLACE_URL)
            with urllib.request.urlopen(req, timeout=10) as r:
                registry = json.loads(r.read())
        except Exception as e:
            return jsonify({'error': f'Failed to fetch registry: {e}'}), 502

        ext_info = None
        for ex in registry.get('extensions', []):
            if ex['id'] == ext_id:
                ext_info = ex
                break
        if not ext_info:
            return jsonify({'error': f'Extension "{ext_id}" not found in marketplace'}), 404

        ext_name = ext_info.get('name', ext_id)
        wanted = (request.args.get('version') or '').strip()
        if not wanted:
            body = request.get_json(silent=True) or {}
            wanted = str(body.get('version') or '').strip()
        versions = _ext_versions(ext_info)
        if not versions:
            return jsonify({'error': 'No download URL for this extension'}), 404
        if wanted:
            picked = next((v for v in versions if v[0] == wanted), None)
            if not picked:
                return jsonify({'error': f'Version "{wanted}" is not published for {ext_id}'}), 404
        else:
            picked = versions[0]
        version, url = picked

        target = os.path.join(EXTENSIONS_DIR, ext_id)
        existing_cfg = os.path.join(target, 'extension.json')
        installed_version = ''
        if os.path.exists(existing_cfg):
            try:
                with open(existing_cfg, encoding='utf-8-sig') as _f:
                    installed_version = str(json.load(_f).get('version') or '')
            except Exception:
                installed_version = ''
            if installed_version == version:
                return jsonify({'exists': True,
                                'message': f'Extension "{ext_name}" {version} is already installed.'})
            _stop_for_replace(ext_id)

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except Exception as e:
            return jsonify({'error': f'Download failed: {e}'}), 502

        backup = None
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            names = zf.namelist()
            mi_ext_config_path = None
            for n in names:
                base = n.split('/')[-1]
                if base == 'extension.json':
                    mi_ext_config_path = n
                    break
            # The wrapper folder is the directory holding extension.json, not the
            # first path segment. A flat archive whose first entry is
            # static/script.js used to be read as "everything lives under
            # static/", which mangled the tree of older published builds.
            prefix = ''
            if mi_ext_config_path and '/' in mi_ext_config_path:
                candidate = mi_ext_config_path.rsplit('/', 1)[0] + '/'
                if all(n.endswith('/') or n.startswith(candidate) for n in names):
                    prefix = candidate
            mi_config = None
            if mi_ext_config_path:
                mi_config = json.loads(zf.read(mi_ext_config_path))
            mi_static_assets = set(mi_config.get('js_modules', []) + mi_config.get('css_modules', [])) if mi_config else set()

            if os.path.isdir(target):
                backup = _backup_target(ext_id)
                for attempt in range(6):
                    try:
                        os.replace(target, backup)
                        break
                    except OSError:
                        _kill_locks(target, ext_id)
                        if attempt == 5:
                            raise
                        time.sleep(0.5)

            os.makedirs(target, exist_ok=True)
            for n in names:
                if n.endswith('/'):
                    continue
                rel = n[len(prefix):] if prefix and n.startswith(prefix) else n
                if not rel:
                    continue
                if '..' in rel.split('/') or rel.startswith('/') or os.path.isabs(rel):
                    raise ValueError(f'unsafe path in archive: {n}')
                if rel in mi_static_assets and not rel.startswith('static/'):
                    rel = os.path.join('static', rel)
                dest = os.path.join(target, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as out:
                    out.write(zf.read(n))
            zf.close()
        except Exception as e:
            _restore_backup(target, backup, ext_id)
            return jsonify({'error': f'Install failed: {e}'}), 500

        t = threading.Thread(target=_bg_install_mkt,
                             args=(ext_id, target, ext_name, version, backup, socketio),
                             daemon=True)
        t.start()
        log.info("Marketplace installing: %s %s (background)", ext_id, version)
        return jsonify({'status': 'installing', 'id': ext_id, 'name': ext_name,
                        'version': version, 'previous': installed_version})

    # ── Providers ──────────────────────────────────────────────────

    @app.route('/api/providers', methods=['GET'])
    def api_providers_list():
        return jsonify({'providers': _load_providers()})

    @app.route('/api/providers', methods=['POST'])
    def api_providers_add():
        data = request.get_json(force=True, silent=True) or {}
        url = (data.get('url') or '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        if not url.startswith('http://') and not url.startswith('https://'):
            return jsonify({'error': 'Invalid URL'}), 400
        providers = _load_providers()
        for p in providers:
            if p.get('url') == url:
                return jsonify({'error': 'Provider already exists'}), 409
        name = data.get('name', '') or url.split('//')[-1].split('/')[0]
        providers.append({'url': url, 'name': name})
        _save_providers(providers)
        return jsonify({'providers': providers})

    @app.route('/api/providers/<int:idx>', methods=['DELETE'])
    def api_providers_remove(idx):
        providers = _load_providers()
        if idx < 0 or idx >= len(providers):
            return jsonify({'error': 'Invalid index'}), 400
        providers.pop(idx)
        _save_providers(providers)
        return jsonify({'providers': providers})

    @app.route('/api/providers/extensions')
    def api_providers_extensions():
        url = request.args.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        if not _is_safe_url(url):
            return jsonify({'error': 'URL must be HTTPS and cannot point to private/internal addresses'}), 400
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    @app.route('/api/providers/install', methods=['POST'])
    def api_providers_install():
        data = request.get_json(force=True, silent=True) or {}
        provider_url = (data.get('provider_url') or '').strip()
        ext_id = (data.get('ext_id') or '').strip()
        if not provider_url or not ext_id:
            return jsonify({'error': 'provider_url and ext_id are required'}), 400
        if not _is_safe_url(provider_url):
            return jsonify({'error': 'provider_url must be HTTPS and cannot point to private/internal addresses'}), 400
        try:
            req = urllib.request.Request(provider_url)
            with urllib.request.urlopen(req, timeout=10) as r:
                registry = json.loads(r.read())
        except Exception as e:
            return jsonify({'error': f'Failed to fetch registry: {e}'}), 502
        ext_info = None
        for ex in registry.get('extensions', []):
            if ex.get('id') == ext_id:
                ext_info = ex
                break
        if not ext_info:
            return jsonify({'error': f'Extension "{ext_id}" not found in provider'}), 404
        download_url = ext_info.get('download_url')
        if not download_url:
            return jsonify({'error': 'No download_url for this extension'}), 400
        if not _is_safe_url(download_url):
            return jsonify({'error': 'download_url must be HTTPS and cannot point to private/internal addresses'}), 400
        target = os.path.join(EXTENSIONS_DIR, ext_id)
        existing_cfg = os.path.join(target, 'extension.json')
        if os.path.exists(existing_cfg):
            try:
                with open(existing_cfg, encoding='utf-8-sig') as _f:
                    _existing = json.load(_f)
                if _existing.get('id') == ext_id:
                    return jsonify({'exists': True, 'message': f'Extension "{ext_info.get("name", ext_id)}" has already been imported before and cannot be imported again.'})
            except Exception:
                pass
            shutil.rmtree(target, ignore_errors=True)
        elif os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
        os.makedirs(target, exist_ok=True)
        try:
            req = urllib.request.Request(download_url)
            with urllib.request.urlopen(req, timeout=30) as r:
                zip_data = r.read()
            import zipfile as _zipfile, io as _io
            with _zipfile.ZipFile(_io.BytesIO(zip_data)) as zf:
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(target, member))
                    target_real = os.path.realpath(target)
                    if not member_path.startswith(target_real):
                        raise ValueError(f"Zip Slip: {member} escapes target directory")
                zf.extractall(target)
        except Exception as e:
            shutil.rmtree(target, ignore_errors=True)
            return jsonify({'error': f'Download failed: {e}'}), 500

        def _bg_load():
            try:
                _sync_extension_lib(target)
                _ensure_extension_deps_async(target, ext_id)
                _load_single_extension(ext_id)
                socketio.emit('extension_install_progress', {'id': ext_id, 'step': 'done'})
            except Exception as e:
                log.error("Provider install bg error: %s", e)
                socketio.emit('extension_install_progress', {'id': ext_id, 'step': 'error', 'error': str(e)})
        threading.Thread(target=_bg_load, daemon=True).start()
        return jsonify({'status': 'installing', 'id': ext_id})

    from coreframe.extensions import failed_extensions
