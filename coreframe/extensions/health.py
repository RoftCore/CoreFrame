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
    quarantined: bool = False
    last_restart_attempt: float = 0.0


class ExtensionIsolation:
    """Per-extension isolation with timeout, health monitoring, and auto-recovery."""

    MAX_LOAD_TIME = 60.0
    MAX_HEARTBEAT_AGE = 60.0
    MAX_RESTARTS = 3
    RESTART_COOLDOWN = 10.0
    RESTART_BACKOFF = (10.0, 30.0, 120.0)
    MONITOR_TICK = 2.0
    # A tick this much longer than MONITOR_TICK means the machine slept, not
    # that the extensions died. Well above any scheduler hiccup, well below
    # MAX_HEARTBEAT_AGE so the guard runs before the fleet is degraded.
    SUSPEND_GAP = 30.0

    def __init__(self):
        self.health: Dict[str, ExtensionHealth] = {}
        self._executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix='ext-load')
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        self._socketio = None  # Set by websocket module after init
        # A second construction resets _socketio and only set_socketio restores it.
        log.info("[isolation] ExtensionIsolation constructed id=%x", id(self))

    def set_socketio(self, socketio):
        self._socketio = socketio
        log.info("[isolation] socketio bound id=%x -> %s", id(self), type(socketio).__name__)

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
        last = time.monotonic()
        while not self._stop_monitor.is_set():
            time.sleep(self.MONITOR_TICK)
            now = time.monotonic()
            gap = now - last
            last = now
            self._check_health(gap)

    def _restamp_after_suspend(self, gap):
        """The machine slept: every heartbeat is stale by the same amount.

        time.monotonic() keeps counting through an OS suspend, so the first tick
        after a wake found every extension hours past MAX_HEARTBEAT_AGE, degraded
        the whole fleet at once and burned the restart budget until they were
        quarantined for the session (log 2026-11-10 10:03 and 10:26, both right
        after a resume). The children were suspended too, so re-stamp instead of
        restarting them. A child that really died while the lid was closed still
        times out normally 60 s later.
        """
        now = time.monotonic()
        with self._lock:
            healed = 0
            for health in self.health.values():
                if health.status in ('healthy', 'degraded'):
                    health.last_heartbeat = now
                    healed += 1
                # The sleep is not backoff: without this a pending restart fires
                # the instant the machine wakes, on a fleet still warming up.
                if health.last_restart_attempt:
                    health.last_restart_attempt += gap
            log.info("[isolation] monitor tick gap %.0fs (suspend/resume), %d heartbeats re-stamped",
                     gap, healed)

    def _check_health(self, gap=0.0):
        now = time.monotonic()
        if gap >= self.SUSPEND_GAP:
            self._restamp_after_suspend(gap)
            now = time.monotonic()
        with self._lock:
            for ext_id, health in list(self.health.items()):
                if health.status == 'dead':
                    continue
                if health.status == 'healthy' and health.last_heartbeat > 0:
                    if now - health.last_heartbeat > self.MAX_HEARTBEAT_AGE:
                        log.warning("Extension %s heartbeat timeout, marking degraded", ext_id)
                        health.status = 'degraded'
                if health.status == 'degraded' and not health.quarantined:
                    if health.restart_count >= self.MAX_RESTARTS:
                        health.quarantined = True
                        health.status = 'dead'
                        log.warning("Extension %s quarantined for session after %d failed restarts",
                                    ext_id, health.restart_count)
                    else:
                        delay = self.RESTART_BACKOFF[min(health.restart_count, len(self.RESTART_BACKOFF) - 1)]
                        if now - health.last_restart_attempt >= delay:
                            log.info("Auto-restarting degraded extension %s (attempt %d/%d)",
                                     ext_id, health.restart_count + 1, self.MAX_RESTARTS)
                            health.last_restart_attempt = now
                            self._schedule_restart(ext_id)

    def _schedule_restart(self, ext_id: str):
        health = self.health.get(ext_id)
        if not health:
            return
        health.cancel_event.set()
        health.restart_count += 1
        attempt = health.restart_count
        health.status = 'loading'
        health.load_time = 0.0
        health.cancel_event = threading.Event()
        if self._socketio:
            self._socketio.emit('extension_restart', {'id': ext_id, 'attempt': attempt})

        # The event has no frontend handler, so the server must do the reload itself.
        def _reload():
            try:
                from coreframe.extensions.loader import _load_single_extension
                ok = _load_single_extension(ext_id)
                log.info("Auto-restart of %s (attempt %d/%d) %s",
                         ext_id, attempt, self.MAX_RESTARTS,
                         'succeeded' if ok else 'failed')
                if not ok:
                    cur = self.health.get(ext_id)
                    if cur is not None:
                        cur.status = 'dead'
                        cur.last_error = 'Auto-restart failed'
            except Exception as e:
                log.warning("Auto-restart of %s raised %s", ext_id, e)

        threading.Thread(target=_reload, daemon=True,
                         name='ext-restart-%s' % ext_id).start()

    def start_load(self, ext_id: str, loader_fn: Callable[[], bool],
                   restart_count: int = 0, quarantined: bool = False) -> threading.Thread:
        # Carried by the auto-restart path; a fresh health would reset the MAX_RESTARTS budget.
        health = ExtensionHealth(ext_id=ext_id, restart_count=restart_count,
                                 quarantined=quarantined)
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
            if not health:
                return
            # A quarantined extension that is still talking is not dead. The
            # quarantine came from a false timeout (a sleep cycle or a stalled
            # monitor), the process never stopped, and its widgets kept working
            # under a badge that said dead. Admit it back.
            if health.quarantined:
                health.quarantined = False
                health.restart_count = 0
                health.status = 'healthy'
                health.last_error = ''
                health.last_heartbeat = time.monotonic()
                log.info("Extension %s answered after quarantine, cleared", ext_id)
                return
            if health.status in ('healthy', 'degraded'):
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
                'quarantined': health.quarantined,
            }

    def get_all_status(self) -> dict:
        with self._lock:
            return {ext_id: self.get_status(ext_id) for ext_id in self.health}
