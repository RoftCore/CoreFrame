import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Optional, Dict, Callable

from coreframe.config import log


@dataclass
class ExtensionHealth:
    ext_id: str
    status: str = 'loading'  # loading, healthy, degraded, dead
    load_time: float = 0.0
    last_heartbeat: float = 0.0
    error_count: int = 0
    last_error: str = ''
    restart_count: int = 0
    load_thread: Optional[threading.Thread] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


class ExtensionIsolation:
    """Per-extension isolation with timeout, health monitoring, and auto-recovery."""

    MAX_LOAD_TIME = 60.0
    MAX_HEARTBEAT_AGE = 60.0
    MAX_RESTARTS = 3
    RESTART_COOLDOWN = 10.0

    def __init__(self):
        self.health: Dict[str, ExtensionHealth] = {}
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='ext-load')
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        self._socketio = None  # Set by websocket module after init

    def set_socketio(self, socketio):
        self._socketio = socketio

    def start_monitor(self):
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_monitor.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name='ext-health-monitor')
            self._monitor_thread.start()

    def stop_monitor(self):
        self._stop_monitor.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _monitor_loop(self):
        while not self._stop_monitor.is_set():
            time.sleep(2.0)
            self._check_health()

    def _check_health(self):
        now = time.monotonic()
        with self._lock:
            for ext_id, health in list(self.health.items()):
                if health.status == 'dead':
                    continue
                if health.status == 'healthy' and health.last_heartbeat > 0:
                    if now - health.last_heartbeat > self.MAX_HEARTBEAT_AGE:
                        log.warning("Extension %s heartbeat timeout, marking degraded", ext_id)
                        health.status = 'degraded'
                if health.status == 'degraded' and health.restart_count < self.MAX_RESTARTS:
                    if now - health.last_heartbeat > self.RESTART_COOLDOWN:
                        log.info("Auto-restarting degraded extension %s (attempt %d/%d)",
                                 ext_id, health.restart_count + 1, self.MAX_RESTARTS)
                        self._schedule_restart(ext_id)

    def _schedule_restart(self, ext_id: str):
        health = self.health.get(ext_id)
        if not health:
            return
        health.cancel_event.set()
        health.restart_count += 1
        health.status = 'loading'
        health.load_time = 0.0
        health.cancel_event = threading.Event()
        if self._socketio:
            self._socketio.emit('extension_restart', {'id': ext_id, 'attempt': health.restart_count})

    def start_load(self, ext_id: str, loader_fn: Callable[[], bool]) -> threading.Thread:
        health = ExtensionHealth(ext_id=ext_id)
        with self._lock:
            self.health[ext_id] = health

        def wrapped_loader():
            start = time.monotonic()
            health.load_time = 0.0
            try:
                future = self._executor.submit(loader_fn)
                try:
                    result = future.result(timeout=self.MAX_LOAD_TIME)
                    health.load_time = time.monotonic() - start
                    if result and not health.cancel_event.is_set():
                        health.status = 'healthy'
                        health.last_heartbeat = time.monotonic()
                        log.info("Extension %s loaded in %.2fs", ext_id, health.load_time)
                    else:
                        health.status = 'dead'
                        health.last_error = 'Load cancelled or returned False'
                except FuturesTimeoutError:
                    health.status = 'dead'
                    health.last_error = f'Load timeout ({self.MAX_LOAD_TIME}s)'
                    log.error("Extension %s load timeout after %.1fs", ext_id, self.MAX_LOAD_TIME)
                    future.cancel()
                except Exception as e:
                    health.status = 'dead'
                    health.last_error = str(e)
                    health.error_count += 1
                    log.error("Extension %s load failed: %s", ext_id, e)
            finally:
                health.load_thread = None

        thread = threading.Thread(target=wrapped_loader, daemon=True, name=f'ext-load-{ext_id}')
        health.load_thread = thread
        thread.start()
        return thread

    def heartbeat(self, ext_id: str):
        with self._lock:
            health = self.health.get(ext_id)
            if health and health.status in ('healthy', 'degraded'):
                health.last_heartbeat = time.monotonic()
                if health.status == 'degraded':
                    health.status = 'healthy'

    def mark_dead(self, ext_id: str, error: str = ''):
        with self._lock:
            health = self.health.get(ext_id)
            if health:
                health.status = 'dead'
                health.last_error = error
                health.cancel_event.set()

    def get_status(self, ext_id: str) -> dict:
        with self._lock:
            health = self.health.get(ext_id)
            if not health:
                return {'status': 'unknown'}
            return {
                'status': health.status,
                'load_time': health.load_time,
                'error_count': health.error_count,
                'last_error': health.last_error,
                'restart_count': health.restart_count,
            }

    def get_all_status(self) -> dict:
        with self._lock:
            return {ext_id: self.get_status(ext_id) for ext_id in self.health}
