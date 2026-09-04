import os
import time
from flask import request, jsonify, send_from_directory

from coreframe.config import log, DATA_DIR
from coreframe.routes.widgets import load_widget_state, save_widget_state

ALLOWED_SCENE_IMG = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
MAX_SCENE_IMG_SIZE = 256 * 1024


def _migrate_scenes(state):
    scenes = {
        'default': {
            'label': '\U0001f3ae',
            'name': 'Default',
            'image': None,
            'cols': 12,
            'rows': 6,
            'widgets': {}
        }
    }
    old_layout = state.get('layout') or {}
    old_hidden = state.get('hidden') or {}
    for ext_id, pos in old_layout.items():
        scenes['default']['widgets'][ext_id] = {
            'col': pos.get('col', 1), 'row': pos.get('row', 1),
            'w': pos.get('w', 2), 'h': pos.get('h', 2),
            'hidden': ext_id in old_hidden
        }
    for ext_id in old_hidden:
        if ext_id not in scenes['default']['widgets']:
            scenes['default']['widgets'][ext_id] = {
                'col': 1, 'row': 1, 'w': 2, 'h': 2, 'hidden': True
            }
    state['scenes'] = scenes
    state['activeScene'] = 'default'
    state.pop('layout', None)
    state.pop('hidden', None)
    save_widget_state(state)
    return scenes


def register_scene_routes(app):

    @app.route('/api/scenes')
    def api_get_scenes():
        state = load_widget_state()
        scenes = state.get('scenes')
        if not scenes:
            scenes = _migrate_scenes(state)
        for sid, sc in scenes.items():
            if 'name' not in sc:
                sc['name'] = sid.replace('_', ' ').title()
            if 'cols' not in sc:
                sc['cols'] = 12
            if 'rows' not in sc:
                sc['rows'] = 6
        state['scenes'] = scenes
        active = state.get('activeScene')
        if active not in scenes:
            active = list(scenes.keys())[0] if scenes else None
        return jsonify({'scenes': scenes, 'active': active})

    @app.route('/api/scenes', methods=['POST'])
    def api_create_scene():
        state = load_widget_state()
        scenes = state.get('scenes')
        if not scenes:
            scenes = _migrate_scenes(state)
        n = len(scenes) + 1
        sid = f'scene_{n}'
        while sid in scenes:
            n += 1
            sid = f'scene_{n}'
        scenes[sid] = {'label': 'home', 'name': sid.replace('_', ' ').title(), 'image': None, 'cols': 12, 'rows': 6, 'widgets': {}}
        state['scenes'] = scenes
        save_widget_state(state)
        return jsonify({'ok': True, 'id': sid})

    @app.route('/api/scenes/<scene_id>', methods=['PUT'])
    def api_update_scene(scene_id):
        data = request.get_json(silent=True) or {}
        state = load_widget_state()
        scenes = state.get('scenes') or {}
        if scene_id not in scenes:
            return jsonify({'error': 'Scene not found'}), 404
        if 'label' in data:
            scenes[scene_id]['label'] = data['label']
        if 'name' in data:
            scenes[scene_id]['name'] = data['name']
        if 'image' in data:
            scenes[scene_id]['image'] = data['image']
        if 'cols' in data:
            scenes[scene_id]['cols'] = data['cols']
        if 'rows' in data:
            scenes[scene_id]['rows'] = data['rows']
        state['scenes'] = scenes
        save_widget_state(state)
        return jsonify({'ok': True})

    @app.route('/api/scenes/<scene_id>', methods=['DELETE'])
    def api_delete_scene(scene_id):
        state = load_widget_state()
        scenes = state.get('scenes') or {}
        if scene_id not in scenes:
            return jsonify({'error': 'Scene not found'}), 404
        if len(scenes) <= 1 or scene_id == 'default':
            return jsonify({'error': 'Cannot delete this scene'}), 400
        del scenes[scene_id]
        if state.get('activeScene') == scene_id:
            keys = list(scenes.keys())
            state['activeScene'] = keys[0]
        state['scenes'] = scenes
        save_widget_state(state)
        return jsonify({'ok': True})

    @app.route('/api/scenes/activate', methods=['POST'])
    def api_activate_scene():
        data = request.get_json(silent=True) or {}
        sid = data.get('id')
        state = load_widget_state()
        scenes = state.get('scenes') or {}
        if sid not in scenes:
            return jsonify({'error': 'Scene not found'}), 404
        state['activeScene'] = sid
        save_widget_state(state)
        return jsonify({'ok': True})

    @app.route('/api/scenes/<scene_id>/widgets', methods=['PUT'])
    def api_save_scene_widgets(scene_id):
        data = request.get_json(silent=True) or {}
        state = load_widget_state()
        scenes = state.get('scenes') or {}
        if scene_id not in scenes:
            return jsonify({'error': 'Scene not found'}), 404
        scenes[scene_id]['widgets'] = data.get('widgets', {})
        state['scenes'] = scenes
        save_widget_state(state)
        return jsonify({'ok': True})

    @app.route('/api/scenes/upload-image', methods=['POST'])
    def api_upload_scene_image():
        if 'image' not in request.files:
            return jsonify({'error': 'No image file'}), 400
        f = request.files['image']
        if not f.filename:
            return jsonify({'error': 'Empty filename'}), 400
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext not in ALLOWED_SCENE_IMG:
            return jsonify({'error': f'Invalid format: .{ext}. Allowed: {",".join(sorted(ALLOWED_SCENE_IMG))}'}), 400
        data_bytes = f.read()
        if len(data_bytes) > MAX_SCENE_IMG_SIZE:
            return jsonify({'error': f'Image too large (max {MAX_SCENE_IMG_SIZE//1024} KiB)'}), 400
        name = f'scene_img_{int(time.time()*1000)}.{ext}'
        dest_dir = os.path.join(DATA_DIR, 'scenes')
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, name)
        with open(dest, 'wb') as out:
            out.write(data_bytes)
        return jsonify({'ok': True, 'path': f'/api/scenes/image/{name}'})

    @app.route('/api/scenes/image/<filename>')
    def api_serve_scene_image(filename):
        # Scene backgrounds use timestamp names (scene_img_<ms>.<ext>), so they
        # are content-stable: long-cache to make scene switches free.
        resp = send_from_directory(os.path.join(DATA_DIR, 'scenes'), filename)
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
