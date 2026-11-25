"""Discovery: which directories behave like extensions, and which can never load.

`_scan_candidates` is the single rule the loader and `/api/extensions` share, so
a regression here either promises a load that never happens or hides an
installed extension from every surface.
"""
import json


def test_scanner_finds_a_complete_extension(extension_factory):
    from coreframe.extensions.loader import _scan_candidates
    extension_factory('scan_ok')
    found = dict(_scan_candidates())
    assert 'scan_ok' in found


def test_scanner_skips_a_directory_without_main(extension_factory):
    from coreframe.extensions.loader import _scan_candidates
    path = extension_factory('scan_node_only')
    (path / 'main.py').unlink()
    assert 'scan_node_only' not in dict(_scan_candidates())


def test_unloadable_directory_is_reported_not_hidden(extension_factory):
    from coreframe.extensions.loader import unloadable_candidates
    path = extension_factory('scan_manifest_only')
    (path / 'main.py').unlink()
    reported = {entry[0]: entry for entry in unloadable_candidates()}
    assert 'scan_manifest_only' in reported
    assert reported['scan_manifest_only'][2]


def test_pending_manifests_carry_the_real_manifest(extension_factory):
    from coreframe.extensions.loader import pending_manifests
    extension_factory('scan_pending', manifest_extra={'grid_size': {'w': 3, 'h': 2}})
    pending = pending_manifests()
    assert 'scan_pending' in pending
    assert pending['scan_pending']['widgets']
    assert pending['scan_pending']['grid_size'] == {'w': 3, 'h': 2}


def test_a_manifest_without_id_falls_back_to_the_folder_name(extension_factory):
    from coreframe.extensions.loader import pending_manifests
    path = extension_factory('scan_no_id')
    manifest = json.loads((path / 'extension.json').read_text(encoding='utf-8'))
    manifest.pop('id')
    (path / 'extension.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert 'scan_no_id' in pending_manifests()


def test_a_manifest_without_widgets_gets_no_placeholder(extension_factory):
    from coreframe.extensions.loader import pending_manifests
    extension_factory('scan_no_widgets', widgets=[])
    assert 'scan_no_widgets' not in pending_manifests()
