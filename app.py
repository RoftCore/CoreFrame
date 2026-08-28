"""Root app.py — shim for backward compatibility with run_coreframe.pyw."""
from coreframe.app import app, socketio, start_server, _shutdown_callback
from coreframe.extensions import extensions, failed_extensions

__all__ = ['app', 'socketio', 'start_server', '_shutdown_callback', 'extensions', 'failed_extensions']
