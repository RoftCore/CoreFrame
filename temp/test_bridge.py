"""Test SubprocessBridge isolation with a real extension."""
import sys, json, time, os

sys.path.insert(0, r'E:\Programming\CoreFrame')

from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.health import ExtensionIsolation

config = {
    "id": "system_monitor",
    "name": "System Monitor",
    "main": "main.py",
    "permissions": {"level": 4},
    "refresh_interval": 5000,
    "data_dir": r"E:\Documentos\CoreFrame\data\system_monitor",
    "isolated": True,
}

ext_path = r"E:\Documentos\CoreFrame\extensions\system_monitor"
iso = ExtensionIsolation()
iso.start_monitor()

print("Creating SubprocessBridge...")
bridge = SubprocessBridge(config, ext_path, iso)
print("Bridge created. Testing get_cpu...")

try:
    result = bridge.get_cpu()
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")

print(f"Health: {iso.get_status('system_monitor')}")
time.sleep(65)
print(f"Health after 65s: {iso.get_status('system_monitor')}")
bridge.on_stop()
print("Done")
