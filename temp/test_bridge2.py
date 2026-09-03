"""Test SubprocessBridge with real extensions."""
import sys, json, time, os
sys.path.insert(0, r'E:\Programming\CoreFrame')

from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.health import ExtensionIsolation

iso = ExtensionIsolation()
iso.start_monitor()

extensions = {
    "system_monitor": {
        "config": {"id": "system_monitor", "name": "System Monitor", "main": "main.py",
                    "permissions": {"level": 4}, "refresh_interval": 5000,
                    "data_dir": r"E:\Documentos\CoreFrame\data\system_monitor"},
        "path": r"E:\Documentos\CoreFrame\extensions\system_monitor",
    },
    "network_monitor": {
        "config": {"id": "network_monitor", "name": "Network Monitor", "main": "main.py",
                    "permissions": {"level": 5}, "refresh_interval": 5000,
                    "data_dir": r"E:\Documentos\CoreFrame\data\network_monitor"},
        "path": r"E:\Documentos\CoreFrame\extensions\network_monitor",
    },
}

bridges = {}
for ext_id, info in extensions.items():
    print(f"Loading {ext_id}...")
    b = SubprocessBridge(info["config"], info["path"], iso)
    bridges[ext_id] = b
    print(f"  Loaded. Testing...")

# Test RPC
for ext_id, b in bridges.items():
    try:
        result = b._call("heartbeat", {})
        print(f"  {ext_id} heartbeat: {result}")
    except Exception as e:
        print(f"  {ext_id} heartbeat FAILED: {e}")

print(f"\nHealth: {iso.get_all_status()}")
print("Waiting 70s for heartbeat cycle...")
time.sleep(70)
print(f"Health after 70s: {iso.get_all_status()}")

for ext_id, b in bridges.items():
    b.on_stop()
print("Done")
