import ctypes
import os
import sys

if sys.platform.startswith('win'):
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)
        ctypes.windll.kernel32.FreeConsole()
    nul = open(os.devnull, 'w')
    sys.stdout = nul
    sys.stderr = nul
