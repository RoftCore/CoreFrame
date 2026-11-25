"""The permission table both sides must agree on.

Levels are declared in a manifest, enforced in the child and explained in the
consent modal; if these maps ever disagree the modal promises something the
child does not enforce.
"""


def test_levels_map_both_ways():
    from coreframe.extensions.permissions import PERMISSION_LEVELS, PERMISSION_NAMES
    assert PERMISSION_LEVELS['basic'] == 0
    assert PERMISSION_LEVELS['storage'] == 1
    assert PERMISSION_LEVELS['user_files'] == 2
    assert PERMISSION_LEVELS['network'] == 3
    assert PERMISSION_LEVELS['system'] == 4
    assert PERMISSION_LEVELS['admin'] == 5
    assert PERMISSION_NAMES[0] == 'basic'
    assert PERMISSION_NAMES[5] == 'admin'
    assert set(PERMISSION_NAMES) == set(PERMISSION_LEVELS.values())


def test_every_level_has_a_description_and_a_label():
    from coreframe.extensions.permissions import (
        PERMISSION_DESCRIPTIONS, PERMISSION_LABELS, PERMISSION_LEVELS,
    )
    for level in PERMISSION_LEVELS.values():
        assert level in PERMISSION_DESCRIPTIONS, level
        assert level in PERMISSION_LABELS, level
