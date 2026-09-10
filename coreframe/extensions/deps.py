import logging
import os
import re
import sys
import threading
import importlib.util
import importlib.metadata

from coreframe.config import log, SHARED_LIB_DIR


def _restore_coreframe_logging():
    """Re-attach our log file handler if pip disturbed global logging state.

    Measured: after an in-process `_pip_main()` call, ZERO logging-framework
    lines are ever written again (faulthandler direct-writes continue), so
    every subsequent log.error/log.info is silently lost for the rest of the
    process. Re-add our FileHandler to the CoreFrame logger when missing and
    make sure its effective level still allows INFO.
    """
    try:
        from coreframe.config import LOG_PATH
        core = logging.getLogger('CoreFrame')
        has_file = any(
            isinstance(h, logging.FileHandler)
            and getattr(h, 'baseFilename', '') == LOG_PATH
            for h in list(core.handlers)
        )
        if not has_file:
            fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
            core.addHandler(fh)
            log.info("CoreFrame file logging restored after pip run")
        if core.getEffectiveLevel() > logging.INFO:
            core.setLevel(logging.INFO)
    except Exception:
        pass


def _patch_pip_for_frozen():
    """distlib.resources.finder() only knows standard loaders (SourceFileLoader,
    FileFinder, zipimporter). Under PyInstaller the modules for pip._vendor.distlib
    are loaded by a frozen importer, so finder() raises
    "Unable to locate finder for 'pip._vendor.distlib'". We instead register the
    frozen loader and point ResourceFinder at the extracted package dir in
    _MEIPASS (collect_all('pip') ships those files as data)."""
    if not getattr(sys, 'frozen', False):
        return
    try:
        from pip._vendor.distlib import resources as _dr
    except Exception:
        return
    try:
        import pip._vendor.distlib as _distlib
    except Exception:
        return
    loader = getattr(_distlib, '__loader__', None)
    if loader is None:
        return
    loader_type = type(loader)
    if loader_type in _dr._finder_registry:
        return
    import types
    meipass = getattr(sys, '_MEIPASS', None)
    base = os.path.dirname(os.path.abspath(getattr(_distlib, '__file__', '')))
    if meipass:
        candidate = os.path.join(meipass, 'pip', '_vendor', 'distlib')
        if os.path.isdir(candidate):
            base = candidate

    def _make_finder(module):
        fake = types.ModuleType('pip._vendor.distlib')
        fake.__file__ = os.path.join(base, '__init__.py')
        if os.path.exists(os.path.join(base, '__init__.py')):
            return _dr.ResourceFinder(fake)
        return _dr.ResourceFinder(module)

    _dr._finder_registry[loader_type] = _make_finder
    _dr._finder_cache.clear()
    log.debug("Registered distlib resource finder for frozen loader %s", loader_type)


def _find_distribution(name):
    """Return (canonical name, version) for an installed distribution, if any,
    trying a few name spellings (case/normalization mismatches like
    `SpotipyFree` vs `spotipyfree`)."""
    candidates = {name, name.replace('-', '_'), name.replace('_', '-')}
    for cand in candidates:
        try:
            dist = importlib.metadata.distribution(cand)
            return (dist.metadata.get('Name', cand), dist.version)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _version_satisfies(spec_str, version, name):
    """Check installed `version` against a PEP 440 spec (e.g. '>=2.1.5,<3')."""
    if not spec_str:
        return True
    try:
        from pip._vendor.packaging.specifiers import SpecifierSet
    except Exception:
        return True
    return SpecifierSet(spec_str).contains(version, prereleases=True)


def _compute_missing_deps(ext_path):
    """Parse requirements.txt and return requirement lines not yet satisfied.

    Raises on unreadable requirements.txt (caller decides how to surface it).
    """
    req_path = os.path.join(ext_path, 'requirements.txt')
    if not os.path.exists(req_path):
        return []
    missing = []
    with open(req_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            head = re.split(r'[<>=~!]', line)[0].strip()
            name = re.sub(r'\[.*\]$', '', head).strip()
            if not name:
                continue
            spec_str = line[len(head):].strip()
            mod_name = name.lower().replace('-', '_').replace('.', '_')
            found_dist = _find_distribution(name)
            found_mod = importlib.util.find_spec(mod_name) is not None

            installed_ok = False
            if found_dist:
                installed_ok = _version_satisfies(spec_str, found_dist[1], name)
            elif not spec_str and found_mod:
                installed_ok = True
            if installed_ok:
                continue
            missing.append(line)
    return missing


def _pip_install_missing(missing):
    """Run pip install --prefix SHARED_LIB_DIR in the calling thread.

    Returns (ok, error): ok is True only if pip exits 0/None. Unlike the
    old fire-and-forget behavior, failures are reported, never swallowed.
    """
    _patch_pip_for_frozen()
    try:
        from pip._internal.cli.main import main as _pip_main
        ret = _pip_main([
            'install', '--prefix', SHARED_LIB_DIR,
            '--no-input', '--quiet',
            '--only-binary', ':all:',
        ] + missing)
    except SystemExit as e:
        ret = e.code
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        _restore_coreframe_logging()
    if ret not in (0, None):
        return False, f"pip install exited with code {ret} for: {', '.join(missing)}"
    log.info("pip install ok for: %s", ', '.join(missing))
    return True, ""


def _ensure_extension_deps_async(ext_path, ext_id):
    """Start dependency installation in background, return immediately."""
    try:
        missing = _compute_missing_deps(ext_path)
    except Exception as e:
        log.warning("Cannot read requirements for %s: %s", ext_id, e)
        return
    if not missing:
        return

    def _install_deps():
        log.info("Installing missing deps for %s: %s", ext_id, missing)
        ok, err = _pip_install_missing(missing)
        if ok:
            log.info("Deps installed for %s", ext_id)
        else:
            log.warning("Failed to install deps for %s: %s", ext_id, err)

    threading.Thread(target=_install_deps, daemon=True, name=f'pip-{ext_id}').start()


def _pip_install_supervised(missing, timeout=120):
    """Run pip in a worker and abandon it after `timeout` seconds.

    Frozen pip can hang silently (TLS stalls, AV interception) with no
    exception and no return — which used to leave the install flow stuck
    forever with zero logs. A supervised timeout converts every failure
    mode (hang, crash, exception) into a loud (False, error) that the
    caller turns into rollback + visible error. Never hangs the caller
    beyond `timeout` seconds.
    """
    result = {}

    def _target():
        try:
            result['out'] = _pip_install_missing(missing)
        except BaseException as e:
            result['out'] = (False, f"{type(e).__name__}: {e}")

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        log.warning("pip install abandoned after %ds timeout for: %s", timeout, ', '.join(missing))
        return False, (
            f"pip install timed out after {timeout}s (network or antivirus "
            f"may be blocking PyPI) for: {', '.join(missing)}"
        )
    return result.get('out', (False, "pip worker ended without result"))


def _ensure_extension_deps_sync(ext_path, ext_id, timeout=120):
    """Blocking dependency installation for the install flow.

    Returns (ok, error). The caller (_bg_install) rolls back the extracted
    files + registry entry on failure so a broken dep never leaves a ghost
    install behind.
    """
    try:
        missing = _compute_missing_deps(ext_path)
    except Exception as e:
        return False, f"Cannot read requirements.txt: {e}"
    if not missing:
        return True, ""
    log.info("Installing missing deps for %s: %s", ext_id, missing)
    return _pip_install_supervised(missing, timeout=timeout)


def _ensure_extension_deps(ext_path):
    """Legacy sync version - kept for compatibility."""
    _ensure_extension_deps_async(ext_path, os.path.basename(ext_path))
