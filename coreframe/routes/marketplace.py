import hashlib
import io
import os
import json
import time
import shutil
import zipfile
import urllib.request
import threading
from flask import request, jsonify

from coreframe.config import (log, EXTENSIONS_DIR, MARKETPLACE_URL,
                             MARKETPLACE_DEFAULT_URL, MARKETPLACE_FALLBACK_URL, PROVIDERS_PATH)
from coreframe.utils import _is_safe_url
from coreframe.extensions import extensions, failed_extensions
from coreframe.extensions.loader import _load_single_extension, _sync_extension_lib
from coreframe.extensions.deps import _ensure_extension_deps_async

MARKETPLACE_CACHE = None
MARKETPLACE_CACHE_TIME = 0


def _registry_urls():
    """Configured registry first, then the official Pages host when nothing was overridden."""
    urls = [MARKETPLACE_URL]
    if MARKETPLACE_URL == MARKETPLACE_DEFAULT_URL and MARKETPLACE_FALLBACK_URL not in urls:
        urls.append(MARKETPLACE_FALLBACK_URL)
    return urls


def _fetch_registry(timeout=10):
    """First URL that answers wins; if none does, raise the last error so the panel can show it."""
    last_error = None
    for url in _registry_urls():
        try:
            request_url = urllib.request.Request(url)
            with urllib.request.urlopen(request_url, timeout=timeout) as response:
                return json.loads(response.read())
        except Exception as exc:
            last_error = exc
            if len(_registry_urls()) > 1:
                log.warning("Marketplace fetch failed for %s: %s", url, exc)
    raise last_error


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


# Install machinery lives in marketplace_install.py; imported here for its routes.
from coreframe.routes.marketplace_install import (
    BACKUP_DIR, _stop_for_replace, _kill_locks, _backup_target,
    _restore_backup, _record_version, _bg_install_mkt,
)


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
            data = _fetch_registry()
            MARKETPLACE_CACHE = data
            MARKETPLACE_CACHE_TIME = now
            return jsonify(data)
        except Exception as e:
            log.error("Marketplace fetch failed: %s", e)
            return jsonify({'error': str(e)}), 502

    @app.route('/api/marketplace/install/<ext_id>', methods=['POST'])
    def api_marketplace_install(ext_id):
        try:
            registry = _fetch_registry()
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

        # Integrity before anything touches the disk: a release republished under
        # the same URL is the one thing a reviewed registry cannot see.
        expected_sha = next(
            (str(v.get('sha256') or '').lower() for v in (ext_info.get('versions') or [])
             if str(v.get('version')) == str(version)),
            '',
        )
        if expected_sha:
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != expected_sha:
                log.error("Marketplace integrity check failed for %s %s: registry %s, download %s",
                          ext_id, version, expected_sha, actual_sha)
                return jsonify({'error': (
                    f'Integrity check failed for {ext_name} {version}: the download does not '
                    f'match the hash published in the registry, so nothing was installed. '
                    f'expected {expected_sha[:16]}… got {actual_sha[:16]}…'
                )}), 502

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
            # The wrapper is the dir holding extension.json, not the first path segment (pitfall 48).
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
