import os
import sys
import json
import logging
import threading

# ── Paths ──────────────────────────────────────────────────────────

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if sys.platform.startswith('win'):
    import ctypes
    _CSIDL_PERSONAL = 0x0005
    _SHGFP_TYPE_CURRENT = 0
    _buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, _CSIDL_PERSONAL, None, _SHGFP_TYPE_CURRENT, _buf)
    DATA_DIR = os.path.join(_buf.value, 'CoreFrame')
else:
    DATA_DIR = os.path.join(os.path.expanduser('~'), '.local', 'share', 'CoreFrame')

STATIC_DIR = os.path.join(BASE_DIR, 'static')
EXTENSIONS_DIR = os.path.join(DATA_DIR, 'extensions')
REGISTRY_PATH = os.path.join(DATA_DIR, 'extensions.json')
WIDGET_STATE_PATH = os.path.join(DATA_DIR, 'widget_state.json')
SHARED_LIB_DIR = os.path.join(DATA_DIR, 'lib')
DATA_DATA_DIR = os.path.join(DATA_DIR, 'data')
PROVIDERS_PATH = os.path.join(DATA_DIR, 'providers.json')
LOG_PATH = os.path.join(DATA_DIR, 'coreframe.log')
MARKETPLACE_URL = 'https://raw.githubusercontent.com/RoftCore/extensions-coreframe/main/registry.json'

# Ensure dirs exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXTENSIONS_DIR, exist_ok=True)
os.makedirs(SHARED_LIB_DIR, exist_ok=True)
os.makedirs(DATA_DATA_DIR, exist_ok=True)

# ── Shared lib path ────────────────────────────────────────────────

if SHARED_LIB_DIR not in sys.path:
    if getattr(sys, 'frozen', False) and sys.path and sys.path[0] == getattr(sys, '_MEIPASS', None):
        sys.path.insert(1, SHARED_LIB_DIR)
    else:
        sys.path.insert(0, SHARED_LIB_DIR)

# ── Stale binary cleanup ──────────────────────────────────────────

if getattr(sys, 'frozen', False):
    _bundled_binaries = {'_cffi_backend', '_ctypes', '_ssl', '_sqlite3', '_hashlib', '_bz2', '_lzma'}
    try:
        for f in os.listdir(SHARED_LIB_DIR):
            name, ext = os.path.splitext(f)
            if ext in ('.pyd', '.dll') and name in _bundled_binaries:
                try:
                    os.remove(os.path.join(SHARED_LIB_DIR, f))
                except Exception:
                    pass
    except Exception:
        pass

# ── Logging ────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
    ]
)
log = logging.getLogger('CoreFrame')

# ── Thread-safe widget state lock ─────────────────────────────────

_widget_state_lock = threading.Lock()
