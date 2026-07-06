"""
CoreFrame — Background server process.

Launched by `pythonw coreframe_server.py` from run.py.
Silently starts the Flask server and keeps it alive.
"""

import os
import sys
import json
import logging
from pathlib import Path

for name in ("socketio", "engineio", "werkzeug", "waitress"):
    logging.getLogger(name).setLevel(logging.WARNING)
logging.getLogger().addHandler(logging.NullHandler())

# Config lives next to the launcher or in DATA_DIR
if getattr(sys, 'frozen', False):
    data_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'CoreFrame')
else:
    data_dir = os.path.dirname(os.path.abspath(__file__))

cfg_path = os.path.join(data_dir, 'coreframe.json')
defaults = {"host": "127.0.0.1", "port": 5000}
if os.path.exists(cfg_path):
    try:
        cfg = {**defaults, **json.loads(Path(cfg_path).read_text(encoding="utf-8"))}
    except Exception:
        cfg = dict(defaults)
else:
    cfg = dict(defaults)

import app
app.start_server(host=cfg["host"], port=cfg["port"])
