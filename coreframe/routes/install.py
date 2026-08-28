import io
import os
import sys
import json
import time
import shutil
import zipfile
import threading
from flask import request, jsonify

from coreframe.config import log, EXTENSIONS_DIR, REGISTRY_PATH
from coreframe.extensions import (
    extensions, failed_extensions, _ext_isolation,
    _load_single_extension, _sync_extension_lib, _start_polling,
)
from coreframe.extensions.deps import _ensure_extension_deps, _ensure_extension_deps_async
from coreframe.extensions.loader import _load_extension_core


def register_install_routes(app, socketio):

    @app.route('/api/install_extension', methods=['POST'])
    def api_install_extension():
        if 'extension' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        f = request.files['extension']
        if not f.filename.endswith('.zip'):
            return jsonify({'error': 'File must be a .zip'}), 400
        try:
            zf = zipfile.ZipFile(io.BytesIO(f.read()))
            names = zf.namelist()
            has_subdir = any(n.count('/') >= 1 and n.split('/')[-1] == 'extension.json' for n in names)
            ext_config = None
            ext_main = None
            for n in names:
                base = n.split('/')[-1]
                if base == 'extension.json':
                    ext_config = n
                elif base == 'main.py':
                    ext_main = n
            if not ext_config or not ext_main:
                return jsonify({'error': 'Extension must contain extension.json and main.py'}), 400
            cfg_data = json.loads(zf.read(ext_config))
            ext_id = cfg_data.get('id')
            if not ext_id:
                parts = ext_config.split('/')
                ext_id = parts[0] if len(parts) >= 2 else f.filename.replace('.zip', '')
            ext_name = cfg_data.get('name', ext_id)
            target = os.path.join(EXTENSIONS_DIR, ext_id)
            existing_cfg = os.path.join(target, 'extension.json')
            if os.path.exists(existing_cfg):
                try:
                    with open(existing_cfg, encoding='utf-8-sig') as _f:
                        _existing = json.load(_f)
                    if _existing.get('id') == ext_id:
                        return jsonify({'exists': True, 'message': f'Extension "{ext_name}" has already been imported before and cannot be imported again.'})
                except Exception:
                    pass
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.exists(target):
                shutil.rmtree(target, ignore_errors=True)
            static_assets_install = set(cfg_data.get('js_modules', []) + cfg_data.get('css_modules', []))
            prefix = ''
            if has_subdir and ext_config.count('/') >= 1:
                prefix = ext_config.rsplit('/', 1)[0] + '/'
            os.makedirs(target, exist_ok=True)
            for n in names:
                if n.endswith('/'):
                    continue
                if prefix and n.startswith(prefix):
                    rel = n[len(prefix):]
                elif has_subdir:
                    parts = n.split('/')
                    rel = '/'.join(parts[1:]) if len(parts) >= 2 else parts[-1]
                else:
                    rel = n
                if not rel:
                    continue
                if '..' in rel or rel.startswith('/'):
                    continue
                if rel in static_assets_install and not rel.startswith('static/'):
                    rel = os.path.join('static', rel)
                dest = os.path.join(target, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as out:
                    out.write(zf.read(n))
            zf.close()
            try:
                with open(REGISTRY_PATH, encoding='utf-8') as rf:
                    registry = json.load(rf)
            except (FileNotFoundError, json.JSONDecodeError):
                registry = {}
            registry[ext_id] = {
                'name': ext_name,
                'version': cfg_data.get('version', '1.0'),
                'author': cfg_data.get('author', ''),
                'category': cfg_data.get('category', 'general'),
            }
            with open(REGISTRY_PATH, 'w', encoding='utf-8') as rf:
                json.dump(registry, rf, indent=2)

            def _bg_install(ext_id, ext_path):
                try:
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'syncing'})
                    _sync_extension_lib(ext_path)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'deps'})
                    _ensure_extension_deps(ext_path)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'loading'})
                    if _load_single_extension(ext_id):
                        ext_data = extensions.get(ext_id)
                        if ext_data:
                            _start_polling(ext_id, ext_data)
                        socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'done'})
                    else:
                        err_msg = failed_extensions.get(ext_id, {}).get('loadError', 'Unknown error')
                        socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': err_msg})
                except Exception as e:
                    log.error("Background install failed for %s: %s", ext_id, e)
                    socketio.emit('extension_install_progress', {'id': ext_id, 'name': ext_name, 'step': 'error', 'error': str(e)})

            t = threading.Thread(target=_bg_install, args=(ext_id, target), daemon=True)
            t.start()
            return jsonify({'status': 'installing', 'id': ext_id, 'name': ext_name})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/extensions/<ext_id>', methods=['DELETE'])
    def api_delete_extension(ext_id):
        from coreframe.config import WIDGET_STATE_PATH, DATA_DIR
        ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
        if not os.path.isdir(ext_path):
            return jsonify({'error': 'Extension not found'}), 404

        ext_data = extensions.get(ext_id)
        if ext_data:
            inst = ext_data.get('instance')
            cleanup = getattr(inst, 'cleanup', None)
            if cleanup:
                try:
                    cleanup()
                except Exception as e:
                    log.warning("Cleanup failed for %s: %s", ext_id, e)

        last_err = None
        for attempt in range(5):
            try:
                shutil.rmtree(ext_path)
                break
            except Exception as e:
                last_err = str(e)
                if attempt < 4:
                    time.sleep(0.5)
                else:
                    return jsonify({'error': f'Failed to delete extension files: {last_err}'}), 500

        from coreframe.extensions.loader import _poll_stop_events
        stop_evt = _poll_stop_events.pop(ext_id, None)
        if stop_evt:
            stop_evt.set()
        extensions.pop(ext_id, None)
        failed_extensions.pop(ext_id, None)
        mod_name = f"extensions.{ext_id}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        try:
            from coreframe.extensions.loader import _load_extension_core
            from coreframe.routes.widgets import load_widget_state, save_widget_state
            state = load_widget_state()
            scenes = state.get('scenes')
            if scenes:
                changed = False
                for sid, scene in scenes.items():
                    if isinstance(scene, dict) and ext_id in scene.get('widgets', {}):
                        del scene['widgets'][ext_id]
                        changed = True
                if changed:
                    state['scenes'] = scenes
                    save_widget_state(state)
                    log.info("Cleaned up %s widgets from all scenes", ext_id)
        except Exception as e:
            log.warning("Failed to clean up widgets for %s: %s", ext_id, e)

        try:
            with open(REGISTRY_PATH, encoding='utf-8') as rf:
                registry = json.load(rf)
            registry.pop(ext_id, None)
            with open(REGISTRY_PATH, 'w', encoding='utf-8') as rf:
                json.dump(registry, rf, indent=2)
        except Exception:
            pass

        log.info("Extension deleted: %s", ext_id)
        return jsonify({'ok': True, 'id': ext_id})

    @app.route('/api/package_extension/<ext_id>')
    def api_package_extension(ext_id):
        ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
        if not os.path.isdir(ext_path):
            return jsonify({'error': 'Extension not found'}), 404

        author = request.args.get('author', '').strip()

        config_path = os.path.join(ext_path, 'extension.json')
        config = {}
        try:
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            pass

        try:
            from flask import send_file
            buf = io.BytesIO()
            static_assets = set(config.get('js_modules', []) + config.get('css_modules', []))
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(ext_path):
                    dirs[:] = [d for d in dirs if d not in ('__pycache__', 'Downloads_playlists') and not d.startswith('.')]
                    for f in files:
                        if f.endswith(('.pyc', '.pyo', '.zip', '.mp3', '.webp', '.jpg', '.jpeg', '.png')):
                            continue
                        if f in ('config.json',):
                            continue
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, ext_path)
                        if rel in static_assets and not rel.startswith('static/'):
                            rel = os.path.join('static', rel)
                        zf.write(full, rel)

                if author:
                    config['author'] = author
                zf.writestr('extension.json', json.dumps(config, indent=2))

            buf.seek(0)
            return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{ext_id}.zip')
        except Exception as e:
            return jsonify({'error': str(e)}), 500
