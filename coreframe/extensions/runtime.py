"""Shared mutable state for the extension layer.

Loader and polls both need it, and a state module is the only way to split them
without a circular import: the objects are created here once, then every module
imports the same instance (mutated, never rebound).
"""
import threading

from coreframe.extensions.health import ExtensionIsolation

# Loaded, loaded-but-disabled, failed, and the three consent queues.
extensions = {}
disabled_extensions = {}
failed_extensions = {}
pending_consent = {}
pending_migration = {}
denied_consent = {}

# Poller bookkeeping: the only way to tell a dead poller from a lost event.
_poll_stop_events = {}
_poll_threads = {}
_poll_last_emit = {}
_poll_no_socket_logged = {}
_poll_exit_reason = {}
_poll_thread_event = {}

# Manifests read once from disk to reserve grid space; see pending_manifests().
_pending_scan_cache = {}

# The load waits for the frontend so it can reserve the grid; the timeout covers minimized mode.
_load_gate = threading.Event()
LOAD_START_TIMEOUT = 8.0

_ext_isolation = ExtensionIsolation()
