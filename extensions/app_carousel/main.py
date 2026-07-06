import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'carousel_config.json')


class Extension:
    def __init__(self, config):
        self.config = config

    def get_config(self):
        try:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                return {"value": json.load(f)}
        except (FileNotFoundError, json.JSONDecodeError):
            return {"value": []}

    def save_config(self, data):
        ids = data.get('extensions', [])
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(ids, f, indent=2)
        return {"value": True}
