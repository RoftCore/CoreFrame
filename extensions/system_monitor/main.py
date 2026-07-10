import psutil
import os
import sys

try:
    import GPUtil
    HAS_GPU = True
except ImportError:
    HAS_GPU = False


class Extension:
    def __init__(self, config):
        self.config = config

    def get_cpu(self):
        result = {"percent": psutil.cpu_percent(interval=0.1)}
        if os.name == 'nt':
            try:
                import wmi
                c = wmi.WMI(namespace="root\\OpenHardwareMonitor")
                for s in c.Sensor():
                    if s.SensorType == 'Temperature' and 'CPU' in s.Name:
                        result['temp'] = round(float(s.Value), 1)
                        break
            except:
                pass
            if 'temp' not in result:
                try:
                    import subprocess
                    out = subprocess.run(
                        'wmic /namespace:\\\\root\\wmi PATH MSAcpi_ThermalZoneTemperature get CurrentTemperature /value',
                        shell=True, capture_output=True, text=True, stderr=subprocess.DEVNULL, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW
                    ).stdout
                    for line in out.splitlines():
                        if 'CurrentTemperature' in line and '=' in line:
                            raw = float(line.split('=')[1].strip())
                            temp = round(raw / 10.0 - 273.15, 1)
                            if 0 < temp < 120:
                                result['temp'] = temp
                                break
                except:
                    pass
        else:
            temps = psutil.sensors_temperatures()
            for name, entries in temps.items():
                if entries:
                    result['temp'] = round(entries[0].current, 1)
                    result['temp_label'] = name
                    break
        return {"value": result}

    def get_ram(self):
        mem = psutil.virtual_memory()
        return {"value": {
            "percent": mem.percent,
            "used": mem.used,
            "total": mem.total
        }}

    def get_gpu(self):
        if not HAS_GPU:
            return {"value": {"temp": 0, "load": 0}}
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                g = gpus[0]
                return {"value": {"temp": g.temperature, "load": g.load * 100}}
        except Exception:
            pass
        return {"value": {"temp": 0, "load": 0}}

    def get_disk(self):
        usage = psutil.disk_usage('/')
        return {"value": {
            "percent": usage.percent,
            "free": usage.free,
            "total": usage.total,
            "used": usage.used
        }}

    

    
