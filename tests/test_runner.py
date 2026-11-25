"""The real mechanism: a child process running ext_runner.py over JSON-RPC.

Everything else in this suite tests the host in isolation. This file spawns the
same child the app spawns, so a break in the protocol, the restrictions or the
runner's ready handshake shows up here instead of as a dead widget.
"""
import json

import pytest


def _isolated(path):
    """The manifest plus the flag that makes the bridge use ext_runner."""
    config = json.loads((path / 'extension.json').read_text(encoding='utf-8'))
    config['isolated'] = True
    return config


def test_runner_handshake_and_call(extension_factory):
    from coreframe.extensions.bridge import SubprocessBridge
    path = extension_factory('runner_call')
    bridge = SubprocessBridge(_isolated(path), str(path), None)
    try:
        assert bridge.get_value() == {'value': 'ok'}
    finally:
        bridge.on_stop()


def test_runner_returns_an_error_instead_of_dying(extension_factory):
    from coreframe.extensions.bridge import SubprocessBridge
    path = extension_factory('runner_boom', main_source=(
        'class Extension:\n'
        '    def __init__(self, config):\n'
        '        self.config = config\n'
        '\n'
        '    def explode(self):\n'
        '        raise ValueError("boom")\n'
        '\n'
        '    def get_value(self):\n'
        "        return {'value': 'still-alive'}\n"
    ))
    bridge = SubprocessBridge(_isolated(path), str(path), None)
    try:
        result = bridge.explode()
        assert 'error' in result
        assert 'boom' in result['error']
        # A raising action is not a dead child: the next call still works.
        assert bridge.get_value() == {'value': 'still-alive'}
    finally:
        bridge.on_stop()


def test_a_manifest_without_the_extension_class_fails_loudly(extension_factory):
    """The contract is that the bridge refuses to hand out a dead extension.

    The message is not asserted: on Windows the runner reports "Module has no
    Extension class", while on Linux the child exits before writing to stderr and
    the bridge only has "Runner process died during startup". Both are failures;
    only one of them is diagnosable, which is a separate gap.
    """
    from coreframe.extensions.bridge import SubprocessBridge
    path = extension_factory('runner_no_class', main_source='VALUE = 1\n')
    with pytest.raises(Exception):
        SubprocessBridge(_isolated(path), str(path), None)

