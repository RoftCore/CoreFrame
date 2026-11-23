"""Realtime pollers: visibility, supervision and start/stop.

Split from loader.py by concern: this layer owns the poller life cycle and the
visibility rule, and touches no discovery or consent logic.
"""
import os
import time
import threading

from coreframe.config import log

from coreframe.extensions.runtime import (
    extensions, disabled_extensions, _poll_stop_events, _poll_threads,
    _poll_last_emit, _poll_exit_reason, _poll_thread_event, _ext_isolation,
)


def widget_visible_anywhere(ext_id):
    """True when the widget is not hidden in at least one scene (single source of truth)."""
    try:
        import json as _json
        from coreframe.config import WIDGET_STATE_PATH
        if not os.path.exists(WIDGET_STATE_PATH):
            return True
        with open(WIDGET_STATE_PATH, encoding='utf-8') as f:
            ws = _json.load(f)
        for sc in ws.get('scenes', {}).values():
            w = (sc.get('widgets') or {}).get(ext_id)
            if w and not w.get('hidden'):
                return True
        return False
    except Exception:
        return True


def _exited_while_hidden(ext_id):
    """True when this poller stopped because its widget was hidden everywhere."""
    return (_poll_exit_reason.get(ext_id) or '').startswith('hidden')


def poller_running(ext_id):
    """True only when the tracked thread is alive AND owns the current stop event."""
    th = _poll_threads.get(ext_id)
    if not (th and th.is_alive()):
        return False
    return _poll_thread_event.get(ext_id) is _poll_stop_events.get(ext_id)


def start_polling(ext_id, ext_data):
    """Start realtime polling for an extension when its manifest asks for it."""
    from coreframe.websocket import _poll_extension
    cfg = ext_data['config']
    interval = cfg.get('refresh_interval', 0)
    if cfg.get('realtime', False) and interval > 0 and cfg.get('widgets', []):
        stop_event = threading.Event()
        _poll_stop_events[ext_id] = stop_event
        t = threading.Thread(target=_poll_extension, args=(ext_id, ext_data, interval),
                             name="poll-%s" % ext_id, daemon=True)
        _poll_threads[ext_id] = t
        _poll_thread_event[ext_id] = stop_event
        _poll_exit_reason.pop(ext_id, None)
        _poll_last_emit.pop(ext_id, None)
        t.start()


def resume_hidden_polls():
    """Restart realtime pollers whose widget is visible again but whose thread died hidden."""
    resumed = []
    for ext_id, ext_data in list(extensions.items()):
        cfg = ext_data.get('config') or {}
        if not cfg.get('realtime'):
            continue
        interval = cfg.get('refresh_interval', 0)
        if not interval or not cfg.get('widgets'):
            continue
        if not _exited_while_hidden(ext_id):
            continue
        if poller_running(ext_id):
            continue
        if not widget_visible_anywhere(ext_id):
            continue
        start_polling(ext_id, ext_data)
        resumed.append(ext_id)
    if resumed:
        log.info("Resumed realtime polling for %s (widget visible again)", ', '.join(resumed))
    return resumed


def supervisor_loop():
    """Visibility changes reach the backend through no endpoint, so poll for them."""
    while True:
        time.sleep(2.0)
        try:
            resume_hidden_polls()
        except Exception as e:
            log.debug("poll supervisor: %s", e)


def pollers_status():
    """Per-extension poller liveness, for /api/debug/pollers."""
    from coreframe.websocket import latest_update
    now = time.time()
    _si = getattr(_ext_isolation, '_socketio', None)
    transport = {
        'socketio_bound': _si is not None,
        'socketio_type': type(_si).__name__ if _si is not None else None,
    }
    out = {}
    for ext_id, ev in list(_poll_stop_events.items()):
        src = extensions.get(ext_id) or disabled_extensions.get(ext_id) or {}
        cfg = src.get('config') or {}
        th = _poll_threads.get(ext_id)
        last = _poll_last_emit.get(ext_id)
        entry = {
            'alive': bool(th and th.is_alive()),
            'realtime': bool(cfg.get('realtime')),
            'interval': cfg.get('refresh_interval', 0),
            'widgets': len(cfg.get('widgets', []) or []),
            'has_values': ext_id in latest_update,
            'seconds_since_emit': round(now - last, 1) if last else None,
            'exit_reason': _poll_exit_reason.get(ext_id),
            'visible': widget_visible_anywhere(ext_id),
        }
        entry.update(transport)
        out[ext_id] = entry
    return out


def stop_all_polls(timeout=3.0):
    """Signal every poll thread to exit; must run before any full reload."""
    for _, ev in list(_poll_stop_events.items()):
        try:
            ev.set()
        except Exception:
            pass
    threads = list(_poll_threads.values())
    _poll_stop_events.clear()
    _poll_threads.clear()
    _poll_thread_event.clear()
    _poll_exit_reason.clear()
    deadline = time.time() + timeout
    for t in threads:
        left = deadline - time.time()
        if left <= 0:
            break
        try:
            t.join(left)
        except Exception:
            pass
