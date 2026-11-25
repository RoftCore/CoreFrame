"""The marketplace refuses a download whose bytes do not match the registry.

The registry is reviewed by a person; a release asset can be replaced afterwards.
This is the only check that sees that, so it gets a test of its own.
"""
import io
import json
import zipfile


def _extension_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('mkt_ext/extension.json', json.dumps({
            'id': 'mkt_ext', 'name': 'Marketplace Test', 'version': '1.0',
            'permissions': {'level': 'basic'}, 'widgets': [],
        }))
        archive.writestr('mkt_ext/main.py', (
            'class Extension:\n'
            '    def __init__(self, config):\n'
            '        self.config = config\n'
        ))
    return buffer.getvalue()


def _registry(sha256):
    return {'extensions': [{
        'id': 'mkt_ext',
        'name': 'Marketplace Test',
        'version': '1.0',
        'version_url': 'https://example.invalid/mkt_ext.zip',
        'download_url': 'https://example.invalid/mkt_ext.zip',
        'versions': [{
            'version': '1.0',
            'download_url': 'https://example.invalid/mkt_ext.zip',
            'sha256': sha256,
        }],
    }]}


def _patch_download(monkeypatch, payload):
    from coreframe.routes import marketplace

    class FakeResponse:
        def read(self, *args):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(marketplace.urllib.request, 'urlopen', lambda *a, **k: FakeResponse())


def test_install_refuses_a_hash_mismatch(client, monkeypatch):
    from coreframe.routes import marketplace
    payload = _extension_zip()
    monkeypatch.setattr(marketplace, '_fetch_registry', lambda timeout=10: _registry('0' * 64))
    _patch_download(monkeypatch, payload)

    response = client.post('/api/marketplace/install/mkt_ext?version=1.0')

    assert response.status_code == 502
    error = response.get_json()['error']
    assert 'Integrity check failed' in error
    assert 'nothing was installed' in error


def test_install_accepts_the_published_hash(client, monkeypatch):
    import hashlib
    from coreframe.routes import marketplace
    from coreframe.config import EXTENSIONS_DIR
    payload = _extension_zip()
    monkeypatch.setattr(marketplace, '_fetch_registry',
                        lambda timeout=10: _registry(hashlib.sha256(payload).hexdigest()))
    _patch_download(monkeypatch, payload)

    response = client.post('/api/marketplace/install/mkt_ext?version=1.0')

    assert response.status_code in (200, 202), response.get_json()
    assert 'Integrity check failed' not in json.dumps(response.get_json() or {})
    # The route starts a background install; wait for the archive to land on disk.
    import os
    import time
    target = os.path.join(EXTENSIONS_DIR, 'mkt_ext', 'extension.json')
    for _ in range(100):
        if os.path.exists(target):
            break
        time.sleep(0.1)
    assert os.path.exists(target)
