"""
CoreFrame — CLI entry point.

Usage:
  coreframe                     Open desktop app window (server starts if needed)
  coreframe open                Same as above
  coreframe close               Stop the server
  coreframe status              Show server status
  coreframe log                 Tail log (last 50 lines)
  coreframe install             Install: PATH command + scheduled task (admin)
  coreframe remove              Uninstall everything
  coreframe --dev               Start with Flask dev server (foreground, debug)
"""

import argparse
import json
import logging
import logging.handlers
import os
import shutil
import signal
import subprocess as _subprocess
import sys
import time
from pathlib import Path

# ── Hide all subprocess console windows ──
if sys.platform.startswith('win'):
    _SU = _subprocess.STARTUPINFO()
    _SU.dwFlags |= _subprocess.STARTF_USESHOWWINDOW
    _SU.wShowWindow = 0  # SW_HIDE
    _orig_init = _subprocess.Popen.__init__
    def _patched_init(self, *args, **kwargs):
        kwargs.setdefault('startupinfo', _SU)
        return _orig_init(self, *args, **kwargs)
    _subprocess.Popen.__init__ = _patched_init
subprocess = _subprocess

BASE_DIR = Path(__file__).parent
if sys.platform.startswith("win"):
    DATA_DIR = Path.home() / "Documents" / "CoreFrame"
else:
    DATA_DIR = Path.home() / ".local" / "share" / "CoreFrame"
CONFIG_PATH = BASE_DIR / "coreframe.json"
LOG_DIR = BASE_DIR / "logs"
PID_FILE = BASE_DIR / "coreframe.pid"
TASK_NAME = "CoreFrame"
LAUNCHER_DIR = Path.home() / "local" / "bin"
LAUNCHER_PATH = LAUNCHER_DIR / "coreframe.cmd"

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 5000,
    "log_dir": "logs",
    "log_level": "INFO",
    "max_log_size_mb": 10,
    "max_log_files": 5,
}

SCHTASKS_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>CoreFrame - local web dashboard</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <Enabled>true</Enabled>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python}</Command>
      <Arguments>{args}</Arguments>
      <WorkingDirectory>{cwd}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""


def load_config():
    paths = [CONFIG_PATH, DATA_DIR / "coreframe.json"]
    for cfg_path in paths:
        if cfg_path.exists():
            try:
                return {**DEFAULT_CONFIG, **json.loads(cfg_path.read_text(encoding="utf-8"))}
            except Exception:
                pass
    # Create default in BASE_DIR
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    print(f"[*] Created default config: {CONFIG_PATH}")
    return dict(DEFAULT_CONFIG)


def setup_logging(cfg):
    log_dir = Path(cfg.get("log_dir", "logs"))
    if not log_dir.is_absolute():
        # Try DATA_DIR first, fall back to BASE_DIR
        candidate = DATA_DIR / log_dir
        if candidate.parent.exists():
            log_dir = candidate
        else:
            log_dir = BASE_DIR / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, cfg.get("log_level", "INFO").upper(), logging.INFO)
    max_bytes = int(cfg.get("max_log_size_mb", 10)) * 1024 * 1024
    backup_count = int(cfg.get("max_log_files", 5))

    handler = logging.handlers.RotatingFileHandler(
        log_dir / "coreframe.log", maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root.addHandler(console)

    return log_dir


def _read_pid():
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return None


def _write_pid(pid=None):
    PID_FILE.write_text(str(pid or os.getpid()))


def _remove_pid():
    PID_FILE.unlink(missing_ok=True)


def _is_pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _is_server_alive(host, port):
    import urllib.request
    try:
        r = urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=2)
        return r.status == 200
    except Exception:
        return False


def _pythonw():
    """Find pythonw.exe (Windows) or return sys.executable (Linux)."""
    if sys.platform.startswith("win"):
        exe = Path(sys.executable)
        w = exe.with_name("pythonw.exe")
        return str(w) if w.exists() else str(exe)
    return sys.executable


def _find_browser_app():
    if sys.platform.startswith("win"):
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        for name in ("chrome", "msedge"):
            found = shutil.which(name)
            if found:
                return found
    else:
        for name in ("google-chrome", "chromium", "firefox", "brave-browser"):
            found = shutil.which(name)
            if found:
                return found
    return None


# --- Commands ---

def cmd_open(cfg):
    """Open the desktop app window (starts server if needed)."""
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 5000))

    if not _is_server_alive(host, port):
        pythonw = _pythonw()
        script = str(BASE_DIR / "coreframe_server.py")
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            [pythonw, script],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
        _write_pid(proc.pid)
        print(f"[*] CoreFrame starting...")

        import urllib.request as _ur
        deadline = time.time() + 15
        ok = False
        while time.time() < deadline:
            try:
                r = _ur.urlopen(f"http://{host}:{port}/api/health", timeout=2)
                if r.status == 200:
                    ok = True
                    break
            except Exception:
                pass
            time.sleep(0.3)

        if not ok:
            _remove_pid()
            print("[-] Server failed to start. Try: coreframe --dev")
            return 1

    browser = _find_browser_app()
    if browser:
        args = [browser, f"http://{host}:{port}"]
        if sys.platform.startswith("win"):
            args = [browser, f"--app=http://{host}:{port}"]
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        print(f"[*] CoreFrame opened — close window or run 'coreframe close'")
    else:
        import webbrowser
        webbrowser.open(f"http://{host}:{port}")
        print("[*] No app-mode browser found, opened in default browser")


def _kill_pid(pid):
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                       capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        os.kill(pid, signal.SIGTERM)

def cmd_close(cfg):
    """Stop the background server."""
    pid = _read_pid()
    if pid and _is_pid_alive(pid):
        try:
            _kill_pid(pid)
            print(f"[+] Server stopped (PID {pid})")
        except Exception as e:
            print(f"[-] Failed to stop: {e}")
    else:
        host = cfg.get("host", "127.0.0.1")
        port = int(cfg.get("port", 5000))
        if _is_server_alive(host, port):
            print("[-] Server running but PID unknown. Close the window manually.")
            return 1
        print("[-] Server is not running")
    _remove_pid()


def cmd_status(cfg):
    """Show server status."""
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 5000))

    # Check by PID
    pid = _read_pid()
    alive = False
    if pid and _is_pid_alive(pid):
        alive = True
        print(f"PID:     {pid} (running)")
    else:
        # Check by health endpoint
        alive = _is_server_alive(host, port)
        if alive:
            print("Server:  running (PID unknown)")

    # Health check
    if alive:
        import urllib.request, json
        try:
            r = urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=3)
            data = json.loads(r.read())
            print(f"URL:     http://{host}:{port}")
            print(f"Health:  OK ({data.get('extensions', 0)} extensions, {data.get('clients', 0)} clients)")
        except Exception as e:
            print(f"Health:  {e}")
    else:
        print("Server:  not running")

    # Check scheduled task
    if sys.platform.startswith("win"):
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"],
                           capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "Status" in line and ":" in line:
                    print(f"Task:    {line.split(':', 1)[1].strip()}")
                    break

    # Check PATH entry
    if LAUNCHER_PATH.exists():
        print(f"PATH:    {LAUNCHER_PATH} (installed)")
    else:
        print(f"PATH:    not installed")
        print(f"         Run 'coreframe install' to add to PATH")


def cmd_log(cfg):
    """Tail the log file."""
    log_dir = Path(cfg.get("log_dir", "logs"))
    if not log_dir.is_absolute():
        log_dir = BASE_DIR / log_dir
    log_file = log_dir / "coreframe.log"

    if not log_file.exists():
        print("[-] No log file found")
        return 1

    lines = log_file.read_text(encoding="utf-8").rstrip().splitlines()
    tail = lines[-50:] if len(lines) > 50 else lines
    for line in tail:
        print(line)


def cmd_install(cfg):
    """Install: PATH command + scheduled task."""
    if not sys.platform.startswith("win"):
        print("[-] install is only supported on Windows")
        return 1

    # 1. Create PATH launcher
    LAUNCHER_DIR.mkdir(parents=True, exist_ok=True)
    launcher_content = f"""@echo off
"{sys.executable}" "{BASE_DIR / 'run.py'}" %*
"""
    LAUNCHER_PATH.write_text(launcher_content)
    print(f"[+] Created: {LAUNCHER_PATH}")
    print(f"    Type 'coreframe' from any terminal")

    # 2. Scheduled task (auto-start on boot) — runs from DATA_DIR
    python = sys.executable
    script = str(BASE_DIR / "run.py") + " open"
    cwd = str(BASE_DIR)

    xml = SCHTASKS_XML.format(python=python, args=f'"{script}"', cwd=cwd)
    xml_path = BASE_DIR / "_task.xml"
    xml_path.write_text(xml, encoding="utf-16")

    r = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
        capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    xml_path.unlink()

    if r.returncode == 0:
        print(f"[+] Scheduled task '{TASK_NAME}' created")
        print(f"    CoreFrame will start automatically on boot (30s delay)")
    else:
        output = (r.stderr or r.stdout or "").strip()
        if "Access is denied" in output:
            print(f"[!] Scheduled task needs admin rights")
            print(f"    Run 'coreframe install' from an Administrator terminal")
        else:
            print(f"[-] Task creation failed: {output}")


def cmd_remove():
    """Uninstall: remove PATH launcher + scheduled task."""
    # 1. Remove PATH launcher
    if LAUNCHER_PATH.exists():
        LAUNCHER_PATH.unlink()
        print(f"[-] Removed: {LAUNCHER_PATH}")
    else:
        print(f"[-] PATH entry not found")

    # 2. Remove scheduled task
    if sys.platform.startswith("win"):
        r = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            print(f"[-] Scheduled task '{TASK_NAME}' removed")
        else:
            output = (r.stderr or r.stdout or "").strip()
            if "does not exist" in output.lower():
                print(f"[-] Task '{TASK_NAME}' not found")
            else:
                print(f"[!] Task removal failed: {output}")
                print(f"    Run 'coreframe remove' from an Administrator terminal")


def _serve(cfg, debug):
    from app import start_server
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 5000))
    mode = "dev" if debug else "running"
    print(f"[*] CoreFrame ({mode}) — http://{host}:{port}")
    start_server(host=host, port=port, debug=debug)

def cmd_dev(cfg):
    """Start Flask dev server (foreground, debug)."""
    _serve(cfg, debug=True)

def cmd_open(cfg):
    """Start CoreFrame server (foreground)."""
    _serve(cfg, debug=False)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="CoreFrame — local web dashboard",
        usage="coreframe [command]\n\nCommands:\n  open       Launch desktop app window (default)\n  close      Stop the server\n  status     Show server status\n  log        Tail log file\n  install    Install PATH command + scheduled task\n  remove     Uninstall everything\n  --dev      Start Flask dev server (foreground)",
    )
    parser.add_argument("command", nargs="?", default="open",
                        help="Command to run (open, close, status, log, install, remove)")
    parser.add_argument("--dev", action="store_true", help="Start with Flask dev server")
    args = parser.parse_args()

    cfg = load_config()
    log_dir = setup_logging(cfg)

    if args.dev:
        return cmd_dev(cfg)

    cmd = args.command.lower()

    if cmd == "open":
        return cmd_open(cfg)
    elif cmd == "close":
        return cmd_close(cfg)
    elif cmd == "status":
        return cmd_status(cfg)
    elif cmd == "log":
        return cmd_log(cfg)
    elif cmd == "install":
        return cmd_install(cfg)
    elif cmd == "remove":
        return cmd_remove()
    else:
        print(f"[-] Unknown command: {cmd}")
        print("    Commands: open, close, status, log, install, remove, --dev")
        return 1


if __name__ == "__main__":
    sys.exit(main())
