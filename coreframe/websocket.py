import time
import threading
from flask_socketio import emit

from coreframe.config import log
from coreframe.extensions import extensions, _ext_isolation

_client_count = 0
latest_update = {}
_poll_stop_events = {}  # Reference to loader's poll stop events


def register_websocket_handlers(socketio, ext_isolation):
    global _client_count

    @socketio.on('connect')
    def handle_connect():
        global _client_count
        _client_count += 1
        log.info("WS client connected (%d)", _client_count)
        if latest_update:
            emit('realtime_update', latest_update)

    @socketio.on('disconnect')
    def handle_disconnect():
        global _client_count
        _client_count = max(0, _client_count - 1)
        log.info("WS client disconnected (%d)", _client_count)

    @socketio.on('focus_window')
    def handle_focus_window():
        emit('focus_window', broadcast=True)
        log.info("Focus window requested from second instance")

    ext_isolation.set_socketio(socketio)


def _poll_extension(ext_id, ext_data, interval_ms):
    inst = ext_data['instance']
    cfg = ext_data['config']
    interval = interval_ms / 1000.0
    next_tick = time.monotonic()
    from coreframe.extensions.loader import _poll_stop_events
    stop_event = _poll_stop_events.get(ext_id)
    while True:
        if stop_event and stop_event.is_set():
            break
        tick = time.monotonic()
        values = {}
        for wDef in cfg.get('widgets', []):
            action = wDef.get('action')
            if not action:
                continue
            try:
                method = getattr(inst, action, None)
                if method:
                    result = method()
                    val = result.get('value') if isinstance(result, dict) else result
                    values[wDef['id']] = val
            except Exception as e:
                log.error("%s/%s: %s", ext_id, action, e)
        if values:
            update = {'ext': ext_id, 'values': values}
            if ext_id == 'system_monitor':
                latest_update.clear()
                latest_update.update(update)
            from coreframe.extensions.loader import _ext_isolation as _ei
            # Use the module-level socketio — will be set by app.py
            _socketio = getattr(_ei, '_socketio', None)
            if _socketio:
                _socketio.emit('realtime_update', update)
        next_tick = max(next_tick + interval, tick + interval)
        remaining = next_tick - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)


def realtime_broadcast():
    from coreframe.extensions.loader import extensions as exts
    for ext_id, ext_data in exts.items():
        from coreframe.extensions.loader import _start_polling
        _start_polling(ext_id, ext_data)
    while True:
        time.sleep(3600)
