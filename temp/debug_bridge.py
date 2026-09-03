"""Debug why SubprocessBridge kills the runner."""
import sys, json, time, os
sys.path.insert(0, r'E:\Programming\CoreFrame')

from coreframe.extensions.bridge import SubprocessBridge
from coreframe.extensions.health import ExtensionIsolation

iso = ExtensionIsolation()
iso.start_monitor()

config = {'id': 'system_monitor', 'name': 'System Monitor', 'main': 'main.py',
          'permissions': {'level': 4}, 'refresh_interval': 5000,
          'data_dir': r'E:\Documentos\CoreFrame\data\system_monitor'}

b = SubprocessBridge(config, r'E:\Documentos\CoreFrame\extensions\system_monitor', iso)
print(f"Created. Poll: {b._proc.poll()}")

# Check config file still exists
if b._config_file:
    print(f"Config file: {b._config_file} exists: {os.path.exists(b._config_file)}")

time.sleep(3)
print(f"After 3s. Poll: {b._proc.poll()}")
if b._proc.poll() is not None:
    err = b._proc.stderr.read()
    print(f"Dead! RC={b._proc.returncode} stderr={err}")

b.on_stop()
