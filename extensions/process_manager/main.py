import os
import sys
import psutil
import io
import base64
from functools import lru_cache
from PIL import Image

if os.name == 'nt':
    import ctypes
    import ctypes.wintypes

    SHGFI_ICON = 0x000000100
    SHGFI_SMALLICON = 0x000000001
    DIB_RGB_COLORS = 0

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ('hIcon', ctypes.wintypes.HANDLE),
            ('iIcon', ctypes.c_int),
            ('dwAttributes', ctypes.c_ulong),
            ('szDisplayName', ctypes.c_wchar * 260),
            ('szTypeName', ctypes.c_wchar * 80),
        ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ('bmType', ctypes.c_long),
            ('bmWidth', ctypes.c_long),
            ('bmHeight', ctypes.c_long),
            ('bmWidthBytes', ctypes.c_long),
            ('bmPlanes', ctypes.c_ushort),
            ('bmBitsPixel', ctypes.c_ushort),
            ('bmBits', ctypes.c_void_p),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_ulong),
            ('biWidth', ctypes.c_long),
            ('biHeight', ctypes.c_long),
            ('biPlanes', ctypes.c_ushort),
            ('biBitCount', ctypes.c_ushort),
            ('biCompression', ctypes.c_ulong),
            ('biSizeImage', ctypes.c_ulong),
            ('biXPelsPerMeter', ctypes.c_long),
            ('biYPelsPerMeter', ctypes.c_long),
            ('biClrUsed', ctypes.c_ulong),
            ('biClrImportant', ctypes.c_ulong),
        ]

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ('fIcon', ctypes.c_bool),
            ('xHotspot', ctypes.c_uint),
            ('yHotspot', ctypes.c_uint),
            ('hbmMask', ctypes.wintypes.HANDLE),
            ('hbmColor', ctypes.wintypes.HANDLE),
        ]

    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    @lru_cache(maxsize=256)
    def _get_exe_icon_b64(exe_path):
        if not exe_path or not os.path.isfile(exe_path):
            return None
        try:
            shinfo = SHFILEINFOW()
            ret = shell32.SHGetFileInfoW(
                exe_path, 0, ctypes.byref(shinfo), ctypes.sizeof(shinfo),
                SHGFI_ICON | SHGFI_SMALLICON
            )
            if not ret or not shinfo.hIcon:
                return None

            hicon = shinfo.hIcon
            icon_size = 16

            bmp_info = BITMAPINFOHEADER()
            bmp_info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmp_info.biWidth = icon_size
            bmp_info.biHeight = -icon_size
            bmp_info.biPlanes = 1
            bmp_info.biBitCount = 32
            bmp_info.biCompression = 0

            pbits = ctypes.c_void_p()
            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bmp_info), DIB_RGB_COLORS, ctypes.byref(pbits), None, 0)
            gdi32.SelectObject(hdc_mem, hbmp)
            user32.DrawIconEx(hdc_mem, 0, 0, hicon, icon_size, icon_size, 0, None, 3)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
            user32.DestroyIcon(hicon)

            buf = (ctypes.c_ubyte * (icon_size * icon_size * 4)).from_address(pbits.value)
            img = Image.frombuffer('RGBA', (icon_size, icon_size), buf, 'raw', 'BGRA', 0, 1)
            buf_io = io.BytesIO()
            img.save(buf_io, format='PNG')
            gdi32.DeleteObject(hbmp)
            return base64.b64encode(buf_io.getvalue()).decode('ascii')
        except Exception:
            return None
else:
    def _get_exe_icon_b64(exe_path):
        return None


class Extension:
    def __init__(self, config):
        self.config = config
        self._disk_cache = {}

    _SKIP = {'System Idle Process', 'Idle'}

    def get_processes(self):
        procs = []
        now = __import__('time').time()
        pids_this_round = set()
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info', 'status', 'username']):
            try:
                info = p.info
                if info['name'] in self._SKIP:
                    continue
                pid = info['pid']
                pids_this_round.add(pid)
                disk = 0
                try:
                    io = p.io_counters()
                    cached = self._disk_cache.get(pid)
                    if cached and io:
                        dt = now - cached['time']
                        if dt > 0:
                            disk = max(0, (io.read_bytes - cached['read_bytes']) / dt) + max(0, (io.write_bytes - cached['write_bytes']) / dt)
                    self._disk_cache[pid] = {'read_bytes': io.read_bytes, 'write_bytes': io.write_bytes, 'time': now}
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
                procs.append({
                    "pid": pid,
                    "name": info['name'] or 'Unknown',
                    "cpu": min(round((info['cpu_percent'] or 0) / psutil.cpu_count(), 1), 100.0),
                    "mem": round(info['memory_percent'] or 0, 1),
                    "mem_rss": info['memory_info'].rss if info['memory_info'] else 0,
                    "disk": round(disk, 0),
                    "user": info['username'] or 'N/A'
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        self._disk_cache = {pid: v for pid, v in self._disk_cache.items() if pid in pids_this_round}
        procs.sort(key=lambda x: x['cpu'], reverse=True)
        return {"value": procs, "system": {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent
        }}

    def get_top_processes(self):
        all_procs = self.get_processes()['value']
        lines = ["{:>5} {:<20} {:>5} {:>5} {}".format("PID", "Name", "CPU%", "MEM%", "Status")]
        lines.append("-" * 50)
        for p in all_procs[:8]:
            lines.append("{:>5} {:<20} {:>5.1f} {:>5.1f} {}".format(
                p['pid'], p['name'][:18], p['cpu'], p['mem'], p['status'][:8]))
        return {"value": "\n".join(lines)}

    def kill_process(self, data):
        pid = data.get('pid')
        if not pid:
            return {"error": "No PID provided"}
        try:
            p = psutil.Process(pid)
            name = p.name()
            if os.name == 'nt':
                p.terminate()
            else:
                p.kill()
            return {"value": f"Process {name} ({pid}) terminated"}
        except psutil.NoSuchProcess:
            return {"error": f"Process {pid} not found"}
        except psutil.AccessDenied:
            return {"error": f"Access denied to kill process {pid}"}
        except Exception as e:
            return {"error": str(e)}

    def get_process_details(self, data):
        pid = data.get('pid')
        if not pid:
            return {"error": "No PID provided"}
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                return {"value": {
                    "pid": p.pid,
                    "name": p.name(),
                    "exe": p.exe(),
                    "cmdline": ' '.join(p.cmdline()) if p.cmdline() else 'N/A',
                    "memory_rss": p.memory_info().rss,
                    "status": p.status(),
                    "username": p.username(),
                    "create_time": p.create_time(),
                    "num_threads": p.num_threads(),
                }}
        except psutil.NoSuchProcess:
            return {"error": "Process not found"}
        except (psutil.AccessDenied, Exception) as e:
            return {"error": str(e)}

    def get_process_icon(self, data):
        pid = data.get('pid')
        if not pid:
            return {"error": "No PID provided"}
        try:
            p = psutil.Process(pid)
            exe = p.exe()
            b64 = _get_exe_icon_b64(exe)
            if b64:
                return {"value": f"data:image/png;base64,{b64}"}
            return {"value": None}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"value": None}
        except Exception:
            return {"value": None}

    def get_icon_by_name(self, data):
        name = data.get('name')
        if not name:
            return {"error": "No name provided"}
        try:
            exe = None
            for p in psutil.process_iter(['name', 'exe']):
                if p.info['name'] and p.info['name'].lower() == name.lower() and p.info['exe']:
                    exe = p.info['exe']
                    break
            if not exe:
                return {"value": None}
            b64 = _get_exe_icon_b64(exe)
            if b64:
                return {"value": f"data:image/png;base64,{b64}"}
            return {"value": None}
        except Exception:
            return {"value": None}
