import concurrent.futures
import threading
import time

from flask_socketio import emit

from coreframe.config import log
from coreframe.extensions import extensions, _ext_isolation
from coreframe.extensions.permissions import get_permission_manager, REQUIRES_CONSENT

_client_count = 0
latest_update = {}  # ext_id -> last realtime payload, replayed to new WS clients
_poll_stop_events = {}  # Reference to loader's poll stop events


def register_websocket_handlers(socketio, ext_isolation):
    global _client_count

    @socketio.on('connect')
    def handle_connect():
        global _client_count
        _client_count += 1
        log.info("WS client connected (%d)", _client_count)
        for update in list(latest_update.values()):
            emit('realtime_update', update)

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
    # Set socketio on permission manager
    perm = get_permission_manager()
    perm.set_socketio(socketio)


def _run_action(inst, wDef, note_error):
    """Run one widget action, never letting it take down the others."""
    action = wDef.get('action')
    method = getattr(inst, action, None)
    if not method:
        return wDef['id'], None
    try:
        result = method()
        val = result.get('value') if isinstance(result, dict) else result
        return wDef['id'], val
    except Exception as e:
        note_error(action, e)
        return wDef['id'], None


# One pool per poller, reused every tick; per-tick pools would churn threads all session.
_action_pools = {}


def _pool(ext_id):
    pool = _action_pools.get(ext_id)
    if pool is None:
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=8, thread_name_prefix='poll-%s' % ext_id)
        _action_pools[ext_id] = pool
    return pool


def _poll_extension(ext_id, ext_data, interval_ms):
    inst = ext_data['instance']
    cfg = ext_data['config']
    interval = interval_ms / 1000.0
    next_tick = time.monotonic()

    # ── Permission check before polling ────────────────────────────
    perm = get_permission_manager()
    required_level = perm.get_required_level(cfg)
    if required_level >= 3 and not perm.check(ext_id, required_level):
        log.warning("Extension %s polling blocked: consent needed at level %d", ext_id, required_level)
        return

    from coreframe.extensions.loader import _poll_stop_events
    stop_event = _poll_stop_events.get(ext_id)
    _err_last_log = 0.0
    _err_count = 0
    def _note_error(action, e):
        nonlocal _err_last_log, _err_count
        _err_count += 1
        now = time.monotonic()
        if now - _err_last_log >= 60.0:
            log.error("%s/%s: %s (repeated %dx, throttled)", ext_id, action, e, _err_count)
            _err_last_log = now
            _err_count = 0
    def _is_visible():
        from coreframe.extensions.loader import widget_visible_anywhere
        return widget_visible_anywhere(ext_id)
    # Every exit is logged; a silent break left widgets on "Loading..." with no cause.
    def _exit(reason):
        log.info("Realtime polling for %s stopped: %s", ext_id, reason)
        try:
            from coreframe.extensions.loader import _poll_exit_reason
            _poll_exit_reason[ext_id] = reason
        except Exception:
            pass

    while True:
        try:
            from coreframe.extensions.loader import _poll_stop_events as _evs, extensions as _exts
            cur = _evs.get(ext_id)
            if cur is not stop_event:
                _exit("replaced by a newer poller")
                break
            if stop_event and stop_event.is_set():
                _exit("stop requested")
                break
            if ext_id not in _exts:
                _exit("extension unloaded")
                break
            if not _is_visible():
# Hidden everywhere -> suspend polling; unhideWidget resumes it.
                _exit("hidden in every scene")
                break
            tick = time.monotonic()
            values = {}
# Actions run concurrently: serially the slowest widget held the whole tick.
            wdefs = [w for w in cfg.get('widgets', []) if w.get('action')]
            if wdefs:
                if len(wdefs) == 1:
                    wid, val = _run_action(inst, wdefs[0], _note_error)
                    if val is not None:
                        values[wid] = val
                else:
                    for wid, val in _pool(ext_id).map(
                            lambda w: _run_action(inst, w, _note_error), wdefs):
                        if val is not None:
                            values[wid] = val
            if values:
                payload = {'ext': ext_id, 'values': values}
                latest_update[ext_id] = payload
                # When it last produced data, for /api/debug/pollers.
                from coreframe.extensions.loader import _poll_last_emit
                _poll_last_emit[ext_id] = time.time()
                from coreframe.extensions.loader import _ext_isolation as _ei
                _ei.heartbeat(ext_id)
                _socketio = getattr(_ei, '_socketio', None)
                if _socketio:
                    _socketio.emit('realtime_update', payload)
                else:
                    # Log once per poller: the tick keeps succeeding, so every other signal says healthy.
                    if not stop_event.is_set():
                        from coreframe.extensions.loader import _poll_no_socket_logged as _nl
                        if not _nl.get(ext_id):
                            _nl[ext_id] = True
                            log.error("Realtime emit for %s has no socketio handle "
                                      "(isolation id=%x): values update the cache but "
                                      "no client ever receives them",
                                      ext_id, id(_ei))
            next_tick = max(next_tick + interval, tick + interval)
            remaining = next_tick - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
        except Exception as e:
            # One bad tick must not cost us the poller for the rest of the session.
            _note_error('tick', e)
            time.sleep(min(interval, 5.0))


def realtime_broadcast():
    from coreframe.extensions.loader import extensions as exts
    # The gated load may have produced nothing yet; a single pass would then start no pollers.
    deadline = time.monotonic() + 30.0
    while not exts and time.monotonic() < deadline:
        time.sleep(0.2)
    for ext_id, ext_data in list(exts.items()):
        from coreframe.extensions.loader import _start_polling
        _start_polling(ext_id, ext_data)
    while True:
        time.sleep(3600)
