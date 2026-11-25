"""The binary carries its legal texts.

A frozen exe redistributes Flask, pywebview, Pillow and friends, and their
licenses require the notices to travel with it. `tools/collect_licenses.py`
copies them into `licenses/`; the spec packs that folder.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_license_index_exists_and_covers_the_runtime_deps():
    index = ROOT / 'licenses' / 'INDEX.md'
    assert index.is_file(), 'run python tools/collect_licenses.py'
    text = index.read_text(encoding='utf-8')
    for package in ('flask', 'werkzeug', 'jinja2', 'click', 'requests', 'pillow',
                    'psutil', 'pywebview', 'urllib3', 'eventlet'):
        assert package in text.lower(), package


def test_the_specs_pack_the_licenses_folder():
    for name in ('CoreFrame.spec', 'CoreFrame-onedir.spec'):
        spec = (ROOT / name).read_text(encoding='utf-8')
        assert "'licenses'" in spec, name
        assert '_legal_datas' in spec, name


def test_every_runtime_dependency_declares_a_license():
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    declared = [line.split('==')[0].strip().lower() for line in requirements.splitlines()
                if line.strip() and not line.startswith('#')]
    index = (ROOT / 'licenses' / 'INDEX.md').read_text(encoding='utf-8').lower()
    for package in declared:
        assert package in index, f'{package} is not in licenses/INDEX.md'
