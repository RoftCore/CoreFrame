import json
import os
import threading
import time
import urllib.request
import webview
from app import start_server

HOST = '127.0.0.1'
PORT = 8420
DATA_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'CoreFrame')
CONFIG_PATH = os.path.join(DATA_DIR, 'coreframe.json')

def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'window_mode': 'windowed'}

def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)

t = threading.Thread(target=start_server, kwargs={'host': HOST, 'port': PORT}, daemon=True)
t.start()

for _ in range(30):
    try:
        urllib.request.urlopen(f'http://{HOST}:{PORT}/api/health', timeout=1)
        break
    except Exception:
        time.sleep(0.5)

config = load_config()
mode = config.get('window_mode', 'windowed')

window = webview.create_window(
    'CoreFrame',
    f'http://{HOST}:{PORT}/?mode={mode}',
    width=1280,
    height=800,
    fullscreen=(mode == 'fullscreen'),
    frameless=(mode == 'frameless'),
)

def set_window_mode(new_mode):
    config = load_config()
    config['window_mode'] = new_mode
    save_config(config)
    gui = window.gui
    uid = window.uid
    try:
        import System.Windows.Forms as WinForms
    except ImportError:
        return
    i = gui.BrowserView.instances.get(uid)
    if not i:
        return
    FS = WinForms.FormBorderStyle
    WS = WinForms.FormWindowState
    # Step 1: always reset to windowed
    if i.is_fullscreen:
        gui.toggle_fullscreen(uid)
    else:
        i.FormBorderStyle = FS.Sizable
        i.WindowState = WS.Normal
    # Step 2: apply requested mode
    if new_mode == 'fullscreen':
        gui.toggle_fullscreen(uid)
    elif new_mode == 'frameless':
        i.FormBorderStyle = getattr(WinForms.FormBorderStyle, 'None')
        i.WindowState = WS.Maximized

window.expose(set_window_mode)
webview.start(private_mode=False)
