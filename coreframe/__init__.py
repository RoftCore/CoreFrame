"""CoreFrame — Personal Control Center.

Attributes are resolved lazily so importing a leaf module (coreframe.config)
does not drag in Flask and the whole server. The launcher needs coreframe.config
early, before webview, and used to duplicate the DATA_DIR resolution because of
this import.
"""

import importlib

__all__ = ['app', 'socketio', 'start_server']


def __getattr__(name):
    if name in __all__:
        mod = importlib.import_module('coreframe.app')
        value = getattr(mod, name)
        globals()[name] = value
        return value
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__():
    return sorted(list(globals()) + __all__)