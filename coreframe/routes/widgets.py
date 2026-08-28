import os
import json
from flask import request, jsonify

from coreframe.config import log, WIDGET_STATE_PATH, _widget_state_lock


def load_widget_state():
    try:
        with open(WIDGET_STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_widget_state(data):
    os.makedirs(os.path.dirname(WIDGET_STATE_PATH), exist_ok=True)
    with _widget_state_lock:
        tmp = WIDGET_STATE_PATH + '.tmp'
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, WIDGET_STATE_PATH)
        except Exception:
            with open(WIDGET_STATE_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)


def register_widget_routes(app):

    @app.route('/api/widget-state')
    def api_get_widget_state():
        try:
            return jsonify(load_widget_state())
        except Exception as e:
            log.error("widget-state GET failed: %s", e)
            return jsonify({'error': str(e)}), 500

    @app.route('/api/widget-state', methods=['POST'])
    def api_set_widget_state():
        try:
            data = request.get_json(silent=True) or {}
            save_widget_state(data)
            return jsonify({'ok': True})
        except Exception as e:
            log.error("widget-state POST failed: %s", e)
            return jsonify({'error': str(e)}), 500
