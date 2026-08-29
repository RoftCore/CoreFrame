import io
import os
import json
import time
import shutil
import zipfile
import urllib.request
import threading
from flask import request, jsonify

from coreframe.config import log, EXTENSIONS_DIR, MARKETPLACE_URL, PROVIDERS_PATH
from coreframe.utils import _is_safe_url
from coreframe.extensions import extensions, _ext_isolation
from coreframe.extensions.loader import _load_single_extension, _sync_extension_lib
from coreframe.extensions.deps import _ensure_extension_deps_async

MARKETPLACE_CACHE = None
MARKETPLACE_CACHE_TIME = 0


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

        url = ext_info.get('download_url')
        if not url:
            return jsonify({'error': 'No download URL for this extension'}), 404

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except Exception as e:
            return jsonify({'error': f'Download failed: {e}'}), 502

        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            names = zf.namelist()
            prefix = ''
            for n in names:
                if n.endswith('/'):
                    continue
                parts = n.split('/')
                if len(parts) >= 2:
                    prefix = parts[0] + '/'
                    break
            mi_config = None
            mi_ext_config_path = None
            for n in names:
                base = n.split('/')[-1]
                if base == 'extension.json':
                    mi_ext_config_path = n
                    break
            if mi_ext_config_path:
                mi_config = json.loads(zf.read(mi_ext_config_path))
            mi_static_assets = set(mi_config.get('js_modules', []) + mi_config.get('css_modules', [])) if mi_config else set()
            os.makedirs(target, exist_ok=True)
            for n in names:
                if n.endswith('/'):
                    continue
                rel = n[len(prefix):] if prefix and n.startswith(prefix) else n
                if rel in mi_static_assets and not rel.startswith('static/'):
                    rel = os.path.join('static', rel)
                dest = os.path.join(target, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as out:
                    out.write(zf.read(n))
            zf.close()

            def _bg_install_mkt(ext_id, target, ext_name):
                try:
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'syncing'})
                    _sync_extension_lib(target)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'deps'})
                    _ensure_extension_deps_async(target, ext_id)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'loading'})
                    if _load_single_extension(ext_id):
                        ext_data = extensions.get(ext_id)
                        if ext_data:
                            from coreframe.extensions.loader import _start_polling
                            _start_polling(ext_id, ext_data)
                        socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'done'})
                    else:
                        err = failed_extensions.get(ext_id, {}).get('loadError', 'Unknown error')
                        socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': str(err)})
                except Exception as e:
                    log.error("Background install failed for %s: %s", ext_id, e)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': str(e)})

            t = threading.Thread(target=_bg_install_mkt, args=(ext_id, target, ext_info.get('name', ext_id)), daemon=True)
            t.start()
            log.info("Marketplace installing: %s (background)", ext_id)
            return jsonify({'status': 'installing', 'id': ext_id, 'name': ext_info.get('name', ext_id)})
        except Exception as e:
            shutil.rmtree(target, ignore_errors=True)
            return jsonify({'error': f'Install failed: {e}'}), 500

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
