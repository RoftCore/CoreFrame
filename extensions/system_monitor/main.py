import psutil
import os

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
                out = subprocess.check_output(
                    'wmic /namespace:\\\\root\\wmi PATH MSAcpi_ThermalZoneTemperature get CurrentTemperature /value',
                    shell=True, stderr=subprocess.DEVNULL, timeout=3
                ).decode()
                for line in out.splitlines():
                    if 'CurrentTemperature' in line and '=' in line:
                        raw = float(line.split('=')[1].strip())
                        temp = round(raw / 10.0 - 273.15, 1)
                        if 0 < temp < 120:
                            result['temp'] = temp
                            break
            except:
                pass
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

    def get_processes(self):
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                procs.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "cpu": round(info['cpu_percent'] or 0, 1),
                    "mem": round(info['memory_percent'] or 0, 1)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x['cpu'], reverse=True)
        return {"value": procs[:20]}

    def free_memory(self):
        if os.name == 'nt':
            import ctypes
            try:
                ctypes.windll.kernel32.SetProcessWorkingSetSize(
                    ctypes.windll.kernel32.GetCurrentProcess(), -1, -1
                )
                return {"value": "Memoria liberada"}
            except Exception as e:
                return {"value": f"Error: {e}"}
        else:
            os.system("sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null")
            return {"value": "Memoria liberada"}
