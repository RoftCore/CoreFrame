import os
import sys
import json
import logging
import logging.handlers
import threading

# Shown in the UI (Settings menu footer). Keep in sync with version_info.txt and
# runner_version_info.txt, which is the file version the binaries carry.
APP_VERSION = '1.1.3'

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

# COREFRAME_DATA_DIR points an install (or a test run) at another data root: the
# tests use it to keep a throwaway tree out of the real one, and a portable copy
# can carry its data next to the exe.
_override_data_dir = os.environ.get('COREFRAME_DATA_DIR')
if _override_data_dir:
    DATA_DIR = os.path.abspath(os.path.expanduser(_override_data_dir))

STATIC_DIR = os.path.join(BASE_DIR, 'static')
EXTENSIONS_DIR = os.path.join(DATA_DIR, 'extensions')
REGISTRY_PATH = os.path.join(DATA_DIR, 'extensions.json')
WIDGET_STATE_PATH = os.path.join(DATA_DIR, 'widget_state.json')
SHARED_LIB_DIR = os.path.join(DATA_DIR, 'lib')
DATA_DATA_DIR = os.path.join(DATA_DIR, 'data')
PROVIDERS_PATH = os.path.join(DATA_DIR, 'providers.json')
LOG_PATH = os.path.join(DATA_DIR, 'coreframe.log')

# Registry CoreFrame reads. The official one is the RoftCore marketplace; the env
# var wins over coreframe.json so a mirror can be tested without editing data.
# The custom domain is canonical; the Pages URL answers while DNS or the
# certificate is not ready, and for a network that cannot resolve the domain.
MARKETPLACE_DEFAULT_URL = 'https://coreframe-marketplace.roftcore.work/registry.json'
MARKETPLACE_FALLBACK_URL = 'https://roftcore.github.io/coreframe-marketplace/registry.json'


def _marketplace_url():
    """Env override, then coreframe.json's marketplace_url, then the official registry."""
    override = os.environ.get('COREFRAME_MARKETPLACE_URL')
    if override and override.startswith(('http://', 'https://')):
        return override
    try:
        with open(os.path.join(DATA_DIR, 'coreframe.json'), encoding='utf-8') as handle:
            url = json.load(handle).get('marketplace_url')
        if url and str(url).startswith(('http://', 'https://')):
            return str(url)
    except Exception:
        pass
    return MARKETPLACE_DEFAULT_URL


MARKETPLACE_URL = _marketplace_url()

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

# Add site-packages from --prefix installs
_site_pkgs = os.path.join(SHARED_LIB_DIR, 'Lib', 'site-packages')
if os.path.isdir(_site_pkgs) and _site_pkgs not in sys.path:
    sys.path.insert(0, _site_pkgs)

# Also check for unix-style path
_site_pkgs_unix = os.path.join(SHARED_LIB_DIR, 'lib', 'python3.11', 'site-packages')
if os.path.isdir(_site_pkgs_unix) and _site_pkgs_unix not in sys.path:
    sys.path.insert(0, _site_pkgs_unix)

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

# Rotating and capped: an unbounded handler grew this to 138 MB of thread dumps (pitfall 28).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=8 * 1024 * 1024, backupCount=3, encoding='utf-8'),
    ]
)
log = logging.getLogger('CoreFrame')

# ── Thread-safe widget state lock ─────────────────────────────────

_widget_state_lock = threading.Lock()
