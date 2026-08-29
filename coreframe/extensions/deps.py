import os
import re
import sys
import threading
import importlib.util
import importlib.metadata

from coreframe.config import log, SHARED_LIB_DIR


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


def _ensure_extension_deps_async(ext_path, ext_id):
    """Start dependency installation in background, return immediately."""
    req_path = os.path.join(ext_path, 'requirements.txt')
    if not os.path.exists(req_path):
        return
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
    if not missing:
        return

    def _install_deps():
        log.info("Installing missing deps for %s: %s", ext_id, missing)
        _patch_pip_for_frozen()
        try:
            from pip._internal.cli.main import main as _pip_main
            _pip_main([
                'install', '--prefix', SHARED_LIB_DIR,
                '--no-input', '--quiet',
                '--only-binary', ':all:',
            ] + missing)
            log.info("Deps installed for %s", ext_id)
        except Exception as e:
            log.warning("Failed to install deps for %s: %s", ext_id, e)

    threading.Thread(target=_install_deps, daemon=True, name=f'pip-{ext_id}').start()


def _ensure_extension_deps(ext_path):
    """Legacy sync version - kept for compatibility."""
    _ensure_extension_deps_async(ext_path, os.path.basename(ext_path))
