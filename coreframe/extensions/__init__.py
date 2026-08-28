from coreframe.extensions.health import ExtensionHealth, ExtensionIsolation
from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.deps import _ensure_extension_deps, _ensure_extension_deps_async
from coreframe.extensions.loader import (
    extensions, failed_extensions, _poll_stop_events, _ext_isolation,
    load_extensions, _load_single_extension, _load_extension_core,
    _sync_extension_lib, _start_polling,
)

__all__ = [
    'ExtensionHealth', 'ExtensionIsolation',
    'SubprocessBridge',
    '_ensure_extension_deps', '_ensure_extension_deps_async',
    'extensions', 'failed_extensions', '_poll_stop_events', '_ext_isolation',
    'load_extensions', '_load_single_extension', '_load_extension_core',
    '_sync_extension_lib', '_start_polling',
]
