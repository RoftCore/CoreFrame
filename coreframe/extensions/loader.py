import os
import sys
import json
import shutil
import importlib.util
import threading

from coreframe.config import (
    log, EXTENSIONS_DIR, DATA_DATA_DIR, SHARED_LIB_DIR
)
from coreframe.extensions.health import ExtensionIsolation
from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.deps import _ensure_extension_deps_async

# Global state — set by app.py
extensions = {}
failed_extensions = {}
_poll_stop_events = {}
_ext_isolation = ExtensionIsolation()


def _sync_extension_lib(ext_path):
    ext_lib = os.path.join(ext_path, 'lib')
    if os.path.isdir(ext_lib):
        for item in os.listdir(ext_lib):
            src = os.path.join(ext_lib, item)
            dst = os.path.join(SHARED_LIB_DIR, item)
            if not os.path.exists(dst):
                if os.path.isdir(src):
                    shutil.copytree(src, dst, ignore_dangling_symlinks=True)
                else:
                    shutil.copy2(src, dst)
                log.debug("Synced %s to shared lib", item)
        try:
            shutil.rmtree(ext_lib)
            log.debug("Removed shipped lib/ from %s", ext_path)
        except Exception:
            pass


def _load_extension_core(ext_id: str, ext_path: str) -> tuple[bool, str]:
    """Core loading logic - returns (success, error_msg)."""
    config_path = os.path.join(ext_path, 'extension.json')
    main_path = os.path.join(ext_path, 'main.py')

    if not os.path.exists(config_path):
        return False, "No extension.json"
    if not os.path.exists(main_path):
        return False, "No main.py"

    try:
        with open(config_path, encoding='utf-8-sig') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"Invalid extension.json: {e}"
    except Exception as e:
        return False, f"Config read error: {e}"

    current_os = 'linux' if not sys.platform.startswith('win') else 'windows'
    platforms = config.get('platforms')
    if platforms is not None and current_os not in platforms:
        return False, f"Platform mismatch: {current_os} not in {platforms}"

    try:
        _sync_extension_lib(ext_path)
        _ensure_extension_deps_async(ext_path, ext_id)
        config['data_dir'] = os.path.join(DATA_DATA_DIR, ext_id)
        lang = config.get('language', 'python')

        if lang != 'python' and lang != 'py':
            ext_instance = SubprocessBridge(config, ext_path, _ext_isolation)
        else:
            mod_name = f"extensions.{ext_id}"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            spec = importlib.util.spec_from_file_location(mod_name, main_path)
            if spec is None or spec.loader is None:
                return False, "Failed to create module spec"
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            if not hasattr(module, 'Extension'):
                return False, "Module has no Extension class"

            ext_instance = module.Extension(config)

        if not hasattr(ext_instance, 'on_stop'):
            log.warning("Extension %s missing on_stop method", ext_id)

        extensions[ext_id] = {'config': config, 'instance': ext_instance}
        failed_extensions.pop(ext_id, None)

        _start_polling(ext_id, extensions[ext_id])

        return True, ""
    except Exception as e:
        mod_name = f"extensions.{ext_id}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        extensions.pop(ext_id, None)
        return False, str(e)


def load_extensions():
    """NON-BLOCKING: Starts async loading of all extensions."""
    log.info("load_extensions: Starting async load (EXTENSIONS_DIR=%s)", EXTENSIONS_DIR)
    _ext_isolation.start_monitor()

    if not os.path.exists(EXTENSIONS_DIR):
        log.info("Extensions dir does not exist: %s", EXTENSIONS_DIR)
        return

    candidates = []
    for name in os.listdir(EXTENSIONS_DIR):
        ext_path = os.path.join(EXTENSIONS_DIR, name)
        if not os.path.isdir(ext_path):
            continue
        config_path = os.path.join(ext_path, 'extension.json')
        main_path = os.path.join(ext_path, 'main.py')
        if os.path.exists(config_path) and os.path.exists(main_path):
            candidates.append((name, ext_path))

    log.info("Found %d candidate extensions", len(candidates))

    for ext_id, ext_path in candidates:
        def make_loader(eid, epath):
            def loader():
                success, error = _load_extension_core(eid, epath)
                if not success:
                    failed_extensions[eid] = {'name': eid, 'loadError': error}
                    _ext_isolation.mark_dead(eid, error)
                    log.error("Extension %s failed: %s", eid, error)
                return success
            return loader

        _ext_isolation.start_load(ext_id, make_loader(ext_id, ext_path))


def _load_single_extension(ext_id):
    """Blocking load for dynamic installs."""
    ext_path = os.path.join(EXTENSIONS_DIR, ext_id)
    config_path = os.path.join(ext_path, 'extension.json')
    if not os.path.exists(config_path):
        return False

    def loader():
        success, error = _load_extension_core(ext_id, ext_path)
        if not success:
            failed_extensions[ext_id] = {'name': ext_id, 'loadError': error}
            _ext_isolation.mark_dead(ext_id, error)
        return success

    thread = _ext_isolation.start_load(ext_id, loader)
    thread.join(timeout=15.0)
    return ext_id in extensions


def _start_polling(ext_id, ext_data):
    """Start realtime polling for an extension if configured."""
    # Lazy import to avoid circular dependency
    from coreframe.websocket import _poll_extension
    cfg = ext_data['config']
    interval = cfg.get('refresh_interval', 0)
    if cfg.get('realtime', False) and interval > 0 and cfg.get('widgets', []):
        stop_event = threading.Event()
        _poll_stop_events[ext_id] = stop_event
        t = threading.Thread(target=_poll_extension, args=(ext_id, ext_data, interval), daemon=True)
        t.start()
