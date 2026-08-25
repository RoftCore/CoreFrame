import json
import sys
import threading
import time


class Extension:
    def __init__(self, config):
        self.config = config
        self._heartbeat_thread = None
        self._stop_heartbeat = threading.Event()
        self._start_heartbeat()
    
    def _start_heartbeat(self):
        """Send periodic heartbeats to CoreFrame for health monitoring."""
        def heartbeat_loop():
            while not self._stop_heartbeat.wait(10.0):  # Every 10 seconds
                try:
                    print(json.dumps({"method": "heartbeat"}), flush=True)
                except Exception:
                    break
        
        self._heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
    
    def on_stop(self):
        """Cleanup when extension is stopped."""
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1.0)
    
    def my_action(self):
        return {"value": 42}
