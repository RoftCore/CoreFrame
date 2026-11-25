"""User state that must survive a rebuild: the disabled flag and the atomic writes.

`extensions.json` is regenerated on boot, so anything the user decided has to
live somewhere else and be written atomically (a truncated file there once
started four disabled extensions).
"""
import json


def test_disabled_flag_persists(extension_factory, data_dir):
    from coreframe.extensions import state
    extension_factory('state_toggle')
    assert state.is_disabled('state_toggle') is False

    state.set_disabled('state_toggle', True)
    assert state.is_disabled('state_toggle') is True
    payload = json.loads((data_dir / 'extensions.state.json').read_text(encoding='utf-8'))
    assert 'state_toggle' in payload['disabled']

    state.set_disabled('state_toggle', False)
    assert state.is_disabled('state_toggle') is False


def test_atomic_write_leaves_no_temp_behind(data_dir):
    from coreframe.extensions import state
    target = data_dir / 'atomic.json'
    state.write_json(str(target), {'value': 1})
    assert json.loads(target.read_text(encoding='utf-8')) == {'value': 1}
    assert not (data_dir / 'atomic.json.tmp').exists()


def test_corrupt_json_is_reported_not_swallowed(data_dir):
    from coreframe.extensions.state import read_json_status
    broken = data_dir / 'broken.json'
    broken.write_text('{not json', encoding='utf-8')
    data, status = read_json_status(str(broken))
    assert data == {}
    assert status == 'corrupt'


def test_missing_file_is_distinguishable_from_corrupt(data_dir):
    from coreframe.extensions.state import read_json_status
    data, status = read_json_status(str(data_dir / 'never-written.json'))
    assert data == {}
    assert status == 'missing'
