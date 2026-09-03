from coreframe.extensions.health import ExtensionHealth, ExtensionIsolation
from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.deps import _ensure_extension_deps, _ensure_extension_deps_async
from coreframe.extensions.permissions import ExtensionPermissionManager, get_permission_manager
from coreframe.extensions.loader import (
    extensions, failed_extensions, pending_consent, pending_migration,
    _poll_stop_events, _ext_isolation,
    load_extensions, _load_single_extension, _load_extension_core,
    _sync_extension_lib, _start_polling, load_after_consent,
)

__all__ = [
    'ExtensionHealth', 'ExtensionIsolation',
    'SubprocessBridge',
    '_ensure_extension_deps', '_ensure_extension_deps_async',
    'ExtensionPermissionManager', 'get_permission_manager',
    'extensions', 'failed_extensions', 'pending_consent', 'pending_migration',
    '_poll_stop_events', '_ext_isolation',
    'load_extensions', '_load_single_extension', '_load_extension_core',
    '_sync_extension_lib', '_start_polling', 'load_after_consent',
]
