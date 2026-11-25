"""Test bootstrap: a throwaway DATA_DIR and one Flask client with the token attached.

`coreframe.config` resolves DATA_DIR at import time, so the override has to be in
the environment before anything imports the package.
"""
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_DATA_DIR = tempfile.mkdtemp(prefix='coreframe-tests-')
os.environ['COREFRAME_DATA_DIR'] = _DATA_DIR

import pytest  # noqa: E402  (must come after the env override)


@pytest.fixture(scope='session')
def data_dir():
    return Path(_DATA_DIR)


@pytest.fixture(scope='session')
def app_module():
    """The real application module.

    `coreframe.app` has to go through importlib: the package's lazy __getattr__
    answers `coreframe.app` with the Flask object, not with the module.
    """
    return importlib.import_module('coreframe.app')


@pytest.fixture(autouse=True)
def fresh_scans():
    """The loader caches its scan; a test that adds an extension must not need a restart."""
    from coreframe.extensions import loader
    loader._pending_scan_cache.clear()
    yield
    loader._pending_scan_cache.clear()


@pytest.fixture()
def client(app_module):
    from coreframe.auth import get_token
    test_client = app_module.app.test_client()
    test_client.environ_base['HTTP_X_COREFRAME_TOKEN'] = get_token()
    return test_client


def make_extension(name, widgets=None, main_source=None, manifest_extra=None):
    """Write a minimal extension into the data dir's extensions folder and return its path."""
    from coreframe.config import EXTENSIONS_DIR
    path = Path(EXTENSIONS_DIR) / name
    path.mkdir(parents=True, exist_ok=True)
    manifest = {
        'id': name,
        'name': name.replace('_', ' ').title(),
        'version': '1.0',
        'author': 'tests',
        'permissions': {'level': 'basic'},
        'widgets': widgets if widgets is not None else [
            {'id': 'value', 'type': 'text', 'label': 'Value', 'action': 'get_value'},
        ],
    }
    manifest.update(manifest_extra or {})
    (path / 'extension.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (path / 'main.py').write_text(main_source or (
        'class Extension:\n'
        '    def __init__(self, config):\n'
        '        self.config = config\n'
        '\n'
        '    def get_value(self):\n'
        "        return {'value': 'ok'}\n"
    ), encoding='utf-8')
    return path


@pytest.fixture()
def extension_factory():
    return make_extension
