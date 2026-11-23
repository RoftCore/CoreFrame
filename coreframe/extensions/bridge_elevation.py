"""UAC elevation: launch coreframe_helper.exe via ShellExecuteW('runas').

The helper takes two temp files (operation in, result out) because elevated
processes cannot share the parent's stdio. Split from bridge.py so the process
supervisor stays one concern.
"""
import ctypes
import json
import os
import sys
import tempfile
import time

# Methods that inherently require admin; bash/exec elevate only when they fail.
_ADMIN_METHODS = {
    'registry_write', 'service_control', 'adapter_control',
    'delete_file',
}


def helper_path():
    """coreframe_helper.exe beside the main executable, or at the project root in dev."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        here = os.path.dirname(os.path.abspath(__file__))        # coreframe/extensions
        base = os.path.dirname(os.path.dirname(here))            # project root
    return os.path.join(base, 'coreframe_helper.exe')


def call_elevated(method, params, timeout=30):
    """Run one admin operation through the helper and return its result dict."""
    if not sys.platform.startswith('win'):
        return {'error': 'Elevation only supported on Windows'}

    helper = helper_path()
    if not os.path.isfile(helper):
        return {'error': f'Helper not found: {helper}'}

    tmp_dir = tempfile.gettempdir()
    ts = int(time.time() * 1000)
    op_file = os.path.join(tmp_dir, f'coreframe_op_{ts}.json')
    result_file = os.path.join(tmp_dir, f'coreframe_result_{ts}.json')

    with open(op_file, 'w', encoding='utf-8') as f:
        json.dump({'type': method, 'params': params or {}}, f)

    try:
        result = _elevated_run(helper, op_file, result_file, timeout)
    except Exception as e:
        result = {'error': f'Elevation failed: {e}'}
    finally:
        for p in (op_file, result_file):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    return result


def _elevated_run(helper_path, op_file, result_file, timeout):
    """ShellExecuteExW('runas') the helper and poll for its result file."""
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    SEE_MASK_NOCLOSEPROCESS = 0x00000040

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ('cbSize', ctypes.c_ulong),
            ('fMask', ctypes.c_ulong),
            ('hwnd', ctypes.c_void_p),
            ('lpVerb', ctypes.c_wchar_p),
            ('lpFile', ctypes.c_wchar_p),
            ('lpParameters', ctypes.c_wchar_p),
            ('lpDirectory', ctypes.c_wchar_p),
            ('nShow', ctypes.c_int),
            ('hInstApp', ctypes.c_void_p),
            ('lpIDList', ctypes.c_void_p),
            ('lpClass', ctypes.c_wchar_p),
            ('hkeyClass', ctypes.c_void_p),
            ('dwHotKey', ctypes.c_ulong),
            ('hIconOrMonitor', ctypes.c_void_p),
            ('hProcess', ctypes.c_void_p),
        ]

    sei = SHELLEXECUTEINFO()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFO)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = 'runas'
    sei.lpFile = helper_path
    sei.lpParameters = f'"{op_file}" "{result_file}"'
    sei.nShow = 0  # SW_HIDE

    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = kernel32.GetLastError()
        if err == 1223:  # ERROR_CANCELLED: user clicked No on UAC
            return {'error': 'UAC denied by user'}
        return {'error': f'ShellExecuteExW failed: error {err}'}

    h_process = sei.hProcess
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            result = _read_result(result_file)
            if result is not None:
                return result
            if kernel32.WaitForSingleObject(h_process, 100) != 258:  # not WAIT_TIMEOUT
                break
        if os.path.exists(result_file):
            result = _read_result(result_file)
            if result is not None:
                return result
    finally:
        kernel32.CloseHandle(h_process)
    return {'error': f'Helper timed out after {timeout}s'}


def _read_result(path):
    """Parsed result file, or None while the helper is still writing it."""
    if not os.path.exists(path):
        return None
    try:
        time.sleep(0.1)
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (ValueError, OSError):
        return None
