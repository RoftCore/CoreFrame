import requests
import socket
import json
import os
import subprocess
import time
import importlib
import inspect
import concurrent.futures
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "vpn_config.json")
PROVIDERS_DIR = os.path.join(BASE, "providers")
DEFAULT_VPN_CONFIG = {
    "provider": "",
    "connect_command": "",
    "disconnect_command": "",
    "adapter_keywords": "vpn,proton,wireguard,wintun,tun,tap",
    "last_action": "",
    "killswitch": False
}

# Known paths for common VPN clients
VPN_CLIENT_PATHS = [
    r"C:\Program Files\Proton\VPN\ProtonVPN.exe",
    r"C:\Program Files\Proton\VPN\Bin\ProtonVPN.exe",
    r"C:\Program Files (x86)\Proton\VPN\ProtonVPN.exe",
    r"C:\Program Files\Proton\VPN\Bin\protonvpn-cli.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Proton\Proton VPN\ProtonVPN.Client.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Proton\Proton VPN\ProtonVPN.exe"),
    r"C:\Program Files\WireGuard\wireguard.exe",
    r"C:\Program Files\OpenVPN\bin\openvpn-gui.exe",
    r"C:\Program Files\NordVPN\NordVPN.exe",
    r"C:\Program Files (x86)\ExpressVPN\expressvpntray.exe",
    r"C:\Program Files\Surfshark\Surfshark.exe",
    r"C:\Program Files\CyberGhost\CyberGhost.exe",
    r"C:\Program Files\TunnelBear\TunnelBear.exe",
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files\Cloudflare\CF-Warp\cloudflare-warp.exe",
    r"C:\Program Files (x86)\LogMeIn Hamachi\hamachi-2.exe",
    r"C:\Program Files\ZeroTier One\zerotier-one.exe",
    r"C:\Program Files\Mullvad VPN\Mullvad VPN.exe",
    r"C:\Program Files\Private Internet Access\pia-client.exe",
    r"C:\Program Files\IPVanish VPN\IPVanish.exe",
    r"C:\Program Files\VyprVPN\VyprVPN.exe",
    r"C:\Program Files\PureVPN\PureVPN.exe",
    r"C:\Program Files\Windscribe\Windscribe.exe",
]

def _load_providers():
    providers = {}
    if not os.path.isdir(PROVIDERS_DIR):
        return providers
    syspath_backup = list(__import__("sys").path)
    __import__("sys").path.insert(0, BASE)
    try:
        for fname in os.listdir(PROVIDERS_DIR):
            if fname.startswith("_") or not fname.endswith(".py"):
                continue
            modname = fname[:-3]
            try:
                mod = importlib.import_module(f"providers.{modname}")
                for name, cls in inspect.getmembers(mod, inspect.isclass):
                    if name == "BaseProvider" or not issubclass(cls, __import__("providers.base", fromlist=["BaseProvider"]).BaseProvider):
                        continue
                    inst = cls()
                    if inst.id:
                        providers[inst.id] = inst
            except Exception:
                pass
    finally:
        __import__("sys").path = syspath_backup
    return providers

PROVIDERS = _load_providers()
_CLI_TARGETS = {p.cli_name.lower() for p in PROVIDERS.values() if p.cli_name}


class Extension:
    def __init__(self, config):
        self.config = config
        self.vpn_config = self._load_vpn_config()
        self._ip_cache = None
        self._ip_cache_time = 0
        self._ports_cache = None
        self._ports_cache_time = 0
        self._vpn_check_cache = None
        self._vpn_check_cache_time = 0
        self._installed_cache = None
        self._installed_cache_time = 0
        self._vpn_detect_cache = None
        self._vpn_detect_cache_time = 0
        self._client_was_running = False

    # --- Helpers ---

    def _get_provider(self, pid=None):
        pid = pid or self.vpn_config.get("provider", "").strip().lower()
        if not pid:
            return None
        if pid in PROVIDERS:
            return PROVIDERS[pid]
        for key in PROVIDERS:
            if key in pid or pid in key:
                return PROVIDERS[key]
        return None

    def _load_vpn_config(self):
        if not os.path.exists(CONFIG_FILE):
            return DEFAULT_VPN_CONFIG.copy()
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            merged = DEFAULT_VPN_CONFIG.copy()
            for k in merged:
                if k in data:
                    merged[k] = data[k]
            return merged
        except Exception:
            return DEFAULT_VPN_CONFIG.copy()

    def _save_vpn_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.vpn_config, f, indent=2, ensure_ascii=False)

    def _vpn_keywords(self):
        raw = self.vpn_config.get("adapter_keywords") or DEFAULT_VPN_CONFIG["adapter_keywords"]
        return [kw.strip().lower() for kw in raw.split(",") if kw.strip()]

    def _active_vpn_adapters(self):
        keywords = self._vpn_keywords()
        active = []
        if HAS_PSUTIL:
            try:
                stats = psutil.net_if_stats()
                for name, stat in stats.items():
                    low = name.lower()
                    if stat.isup and any(kw in low for kw in keywords):
                        active.append(name)
                if active:
                    return active
            except Exception:
                pass
        try:
            r = subprocess.run(["netsh", "interface", "show", "interface"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in r.stdout.splitlines():
                if "Connected" in line or "connected" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        ifname = parts[-1]
                        low = ifname.lower()
                        if any(kw in low for kw in keywords):
                            active.append(ifname)
        except Exception:
            pass
        return active

    def _public_ip_info(self):
        ip = requests.get("https://api.ipify.org", timeout=3).text
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        data = resp.json()
        return ip, data

    def _detect_vpns(self):
        now = time.time()
        if self._vpn_detect_cache and now - self._vpn_detect_cache_time < 30:
            return self._vpn_detect_cache
        installed = set()
        active = set()
        client_targets = {}
        for pid, prov in PROVIDERS.items():
            names = prov.client_names + ([prov.cli_name] if prov.cli_name else [])
            for n in names:
                client_targets[n.lower()] = pid
        for path in VPN_CLIENT_PATHS:
            if os.path.exists(path):
                bn = os.path.basename(path).lower()
                if bn in client_targets:
                    installed.add(client_targets[bn])
        try:
            r = subprocess.run(["sc", "query", "state=all"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            blocks = r.stdout.split("\n\n")
            for pid, prov in PROVIDERS.items():
                for svc in prov.tunnel_services + prov.app_services:
                    svc_lower = svc.lower()
                    for block in blocks:
                        if svc_lower in block.lower():
                            installed.add(pid)
                            if "running" in block.lower():
                                active.add(pid)
                            break
        except Exception:
            pass
        try:
            r = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in r.stdout.splitlines():
                parts = line.strip('"').split('","')
                if len(parts) >= 1:
                    pname = parts[0].strip('"').lower()
                    for pid, prov in PROVIDERS.items():
                        if pname in [p.lower() for p in prov.all_procs + prov.tunnel_procs]:
                            installed.add(pid)
        except Exception:
            pass
        self._vpn_detect_cache = (installed, active)
        self._vpn_detect_cache_time = now
        return installed, active

    def _detect_active_providers(self):
        return self._detect_vpns()[1]

    def _detect_installed_vpns(self):
        return self._detect_vpns()[0]

    def _detect_cli(self, provider_hint=None):
        prov = PROVIDERS.get(provider_hint) if provider_hint else None
        if prov and prov.cli_name:
            name = prov.cli_name.lower()
            for path in VPN_CLIENT_PATHS:
                if os.path.basename(path).lower() == name and os.path.exists(path):
                    return path
            for base in getattr(prov, "_cli_search_dirs", []):
                if os.path.isdir(base):
                    try:
                        for root, dirs, files in os.walk(base):
                            for f in files:
                                if f.lower() == name:
                                    return os.path.join(root, f)
                    except Exception:
                        pass
            # Fallback: si no se encuentra el CLI dedicado, probar client_names
            for client in prov.client_names:
                for path in VPN_CLIENT_PATHS:
                    if os.path.basename(path).lower() == client.lower() and os.path.exists(path):
                        return path
                for base in getattr(prov, "_cli_search_dirs", []):
                    if os.path.isdir(base):
                        try:
                            for root, dirs, files in os.walk(base):
                                for f in files:
                                    if f.lower() == client.lower():
                                        return os.path.join(root, f)
                        except Exception:
                            pass
            return None
        # Fallback: search all known CLI targets
        targets = _CLI_TARGETS
        for path in VPN_CLIENT_PATHS:
            bn = os.path.basename(path).lower()
            if bn in targets and os.path.exists(path):
                if provider_hint:
                    p = PROVIDERS.get(provider_hint)
                    if p and p.cli_name.lower() == bn:
                        return path
                    continue
                return path
        search_dirs = [
            r"C:\Program Files\Proton\VPN\Bin", r"C:\Program Files\Proton\VPN",
            r"C:\Program Files\NordVPN", r"C:\Program Files\Windscribe",
            r"C:\Program Files\Mullvad VPN",
        ]
        for base in search_dirs:
            if os.path.isdir(base):
                try:
                    for root, dirs, files in os.walk(base):
                        for f in files:
                            if f.lower() in targets:
                                if provider_hint:
                                    p = PROVIDERS.get(provider_hint)
                                    if p and p.cli_name.lower() == f.lower():
                                        return os.path.join(root, f)
                                    continue
                                return os.path.join(root, f)
                except Exception:
                    pass
        return None

    def _cli_exec(self, action, target_provider=None):
        if target_provider:
            pids = {target_provider}
        else:
            cfg = self.vpn_config.get("provider", "").strip().lower()
            if cfg:
                pids = {pid for pid in PROVIDERS if pid in cfg or cfg in pid}
            else:
                pids = set()
        if not pids:
            return None
        results = []
        for pid in pids:
            prov = PROVIDERS.get(pid)
            if not prov or not prov.cli_name:
                continue
            if getattr(prov, f"cli_{action}", None) is None:
                continue
            cli_path = self._detect_cli(provider_hint=pid)
            if not cli_path:
                continue
            args = getattr(prov, f"cli_{action}", [])
            if not args:
                continue
        try:
            r = subprocess.run([cli_path] + args, capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            out = (r.stdout + r.stderr).strip()
                results.append({"ok": r.returncode == 0, "provider": pid, "message": out[:200]})
            except Exception as e:
                results.append({"ok": False, "provider": pid, "message": str(e)})
        return results if results else None

    def _cli_connect(self):
        return self._cli_exec("connect")

    def _cli_disconnect(self):
        return self._cli_exec("disconnect")

    def _find_vpn_client(self):
        targets = self._resolve_target_providers()
        if not targets:
            return None
        client_names = list(dict.fromkeys(
            n for pid in targets
            for n in (PROVIDERS.get(pid).client_names if PROVIDERS.get(pid) else [])
        ))
        if not client_names:
            return None
        search_dirs = [
            r"C:\Core\Programs\VPN",
            r"C:\Program Files\Proton\VPN", r"C:\Program Files (x86)\Proton\VPN",
            r"C:\Program Files\WireGuard", r"C:\Program Files\OpenVPN",
            r"C:\Program Files\NordVPN", r"C:\Program Files\Windscribe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Proton\Proton VPN"),
        ]
        target_set = set(n.lower() for n in client_names)
        for base in search_dirs:
            if os.path.isdir(base):
                try:
                    for root, dirs, files in os.walk(base):
                        for f in files:
                            if f.lower() in target_set:
                                return os.path.join(root, f)
                except Exception:
                    pass
        return None

    def _resolve_target_providers(self):
        cfg = self.vpn_config.get("provider", "").strip().lower()
        if cfg:
            for pid in PROVIDERS:
                if pid in cfg or cfg in pid:
                    return {pid}
        return self._detect_active_providers()

    def _target_provider_obj(self):
        targets = self._resolve_target_providers()
        if targets:
            for pid in targets:
                p = PROVIDERS.get(pid)
                if p:
                    return p
        return None

    # --- Connect / Disconnect ---

    def _universal_disconnect(self):
        results = []
        any_ok = False
        targets = self._resolve_target_providers()
        if not targets:
            results.append("no active VPN detected")

        cli_results = self._cli_disconnect()
        if cli_results:
            for cr in cli_results:
                if cr["ok"]:
                    results.append(f"✓ {cr['provider']}: {cr['message']}")
                    any_ok = True
                else:
                    results.append(f"{cr['provider']} CLI: {cr['message']}")

        target_services = list(dict.fromkeys(
            s for pid in targets
            for s in (PROVIDERS.get(pid).tunnel_services if PROVIDERS.get(pid) else [])
        ))
        stopped = []
        for svc in target_services:
            try:
                r = subprocess.run(["sc", "stop", svc], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                out = (r.stdout + r.stderr).lower()
                if r.returncode == 0 or "stopped" in out or "pending" in out or "not running" in out:
                    stopped.append(svc)
                    any_ok = True
            except Exception:
                pass
        if stopped:
            results.append(f"✓ services stopped: {', '.join(stopped)}")

        time.sleep(2)
        still_active = self._active_vpn_adapters()

        try:
            r = subprocess.run(["rasdial", "/d"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode == 0:
                results.append("✓ rasdial: disconnected")
                any_ok = True
                still_active = False
            else:
                results.append(f"rasdial: {(r.stderr or r.stdout or '').strip() or 'no RAS connections'}")
        except Exception as e:
            results.append(f"rasdial: {e}")

        if still_active and targets:
            kw_parts = "+".join(kw for pid in targets for kw in (PROVIDERS.get(pid).keywords if PROVIDERS.get(pid) else []))
            if kw_parts:
                try:
                    r = subprocess.run(f'netsh interface show interface | findstr /i "{kw_parts}"', shell=True, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                    if r.stdout.strip():
                        for line in r.stdout.strip().splitlines():
                            parts = line.split()
                            if len(parts) >= 4 and "connect" in parts[1].lower():
                                ifname = parts[-1]
                                subprocess.run(f'netsh interface set interface name="{ifname}" admin=disabled', shell=True, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                                results.append(f"✓ adapter disabled: {ifname}")
                                any_ok = True
                except Exception as e:
                    results.append(f"netsh disable: {e}")

        if still_active and targets:
            target_procs = list(dict.fromkeys(
                p for pid in targets for p in (PROVIDERS.get(pid).tunnel_procs if PROVIDERS.get(pid) else [])
            ))
            killed = []
            for pname in target_procs:
                try:
                    r = subprocess.run(["taskkill", "/F", "/IM", pname], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                    if r.returncode == 0:
                        killed.append(pname)
                        any_ok = True
                except Exception:
                    pass
            if killed:
                results.append(f"✓ tunnel processes killed: {', '.join(set(killed))}")

        if still_active and targets:
            time.sleep(1)
            if self._active_vpn_adapters():
                target_procs = list(dict.fromkeys(
                    p for pid in targets for p in (PROVIDERS.get(pid).all_procs if PROVIDERS.get(pid) else [])
                ))
                killed = []
                for pname in target_procs:
                    try:
                        r = subprocess.run(["taskkill", "/F", "/IM", pname], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                        if r.returncode == 0:
                            killed.append(pname)
                            any_ok = True
                    except Exception:
                        pass
                if killed:
                    results.append(f"✓ VPN processes killed: {', '.join(set(killed))}")

        cmd = self.vpn_config.get("disconnect_command", "").strip()
        if cmd:
            try:
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                results.append("✓ custom command executed")
                any_ok = True
            except Exception as e:
                results.append(f"custom command: {e}")

        time.sleep(1)
        if not self._active_vpn_adapters():
            results.append("✓ VPN disconnected")
        return {"ok": any_ok, "message": " | ".join(results)}

    def _universal_connect(self):
        results = []
        any_ok = False
        targets = self._resolve_target_providers()
        self._client_was_running = self._is_client_running()
        prov = self._target_provider_obj()

        # Method 1: Start services
        target_services = list(dict.fromkeys(
            s for pid in targets
            for s in (PROVIDERS.get(pid).tunnel_services + PROVIDERS.get(pid).app_services if PROVIDERS.get(pid) else [])
        ))
        started = []
        for svc in target_services:
            try:
                r = subprocess.run(["sc", "start", svc], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                out = (r.stdout + r.stderr).lower()
                if r.returncode == 0 or "already running" in out or "running" in out:
                    started.append(svc)
                    any_ok = True
            except Exception:
                pass
        if started:
            results.append(f"✓ services started: {', '.join(started)}")
        if any_ok:
            time.sleep(2)

        # Method 2: Enable adapters
        kw_parts = "+".join(kw for pid in targets for kw in (PROVIDERS.get(pid).keywords if PROVIDERS.get(pid) else []))
        if kw_parts:
            try:
                r = subprocess.run(f'netsh interface show interface | findstr /i "{kw_parts}"', shell=True, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                if r.stdout.strip():
                    for line in r.stdout.strip().splitlines():
                        parts = line.split()
                        if len(parts) >= 4 and "disabled" in parts[0].lower():
                            ifname = parts[-1]
                            subprocess.run(f'netsh interface set interface name="{ifname}" admin=enabled', shell=True, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                            results.append(f"✓ adapter enabled: {ifname}")
                            any_ok = True
            except Exception as e:
                results.append(f"netsh enable: {e}")

        # Method 3: CLI connect (skip if provider says so)
        if prov and prov.skip_cli_connect:
            prov_msgs = prov.on_connect(self)
            results.extend(prov_msgs)
            if any("connected" in m for m in prov_msgs):
                any_ok = True
        else:
            cli_results = self._cli_connect()
            if cli_results:
                for cr in cli_results:
                    if cr["ok"]:
                        results.append(f"✓ {cr['provider']}: {cr['message']}")
                        any_ok = True
                    else:
                        results.append(f"{cr['provider']} CLI: {cr['message']}")

        # Method 5: rasdial (skip per provider)
        if not (prov and prov.skip_rasdial):
            try:
                r = subprocess.run('rasdial /enum', shell=True, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                for line in (r.stdout or "").splitlines():
                    kw = self._vpn_keywords() + ["conexion", "connection"]
                    if any(k in line.lower() for k in kw):
                        conn_name = line.strip().rstrip(":")
                        subprocess.run(["rasdial", conn_name], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                        results.append(f"✓ rasdial: connecting '{conn_name}'")
                        any_ok = True
                        break
            except Exception as e:
                results.append(f"rasdial enum: {e}")
            provider = self.vpn_config.get("provider", "").strip()
            if provider:
                try:
                    r = subprocess.run(["rasdial", provider], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                    if r.returncode == 0:
                        results.append(f"✓ rasdial: connected '{provider}'")
                        any_ok = True
                    else:
                        results.append(f"rasdial {provider}: {r.stderr.strip() or r.stdout.strip()}")
                except Exception as e:
                    results.append(f"rasdial {provider}: {e}")

        # Method 6: Configured command
        cmd = self.vpn_config.get("connect_command", "").strip()
        if cmd:
            try:
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                results.append("✓ custom command executed")
                any_ok = True
            except Exception as e:
                results.append(f"custom command: {e}")

        time.sleep(3)
        if self._active_vpn_adapters():
            results.append("✓ VPN connected")
            self._flush_dns()
            adapter = self._get_vpn_adapter_name()
            if adapter:
                try:
                    subprocess.run(["netsh", "interface", "ip", "set", "dns", f'name="{adapter}"', "static", "1.1.1.1", "primary"], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                    subprocess.run(["netsh", "interface", "ip", "add", "dns", f'name="{adapter}"', "1.0.0.1", "index=2"], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                    results.append(f"✓ DNS: Cloudflare on {adapter}")
                except Exception:
                    pass
            try:
                subprocess.run(["reg", "add", "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient", "/v", "DisableSmartNameResolution", "/t", "REG_DWORD", "/d", "1", "/f"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                results.append("✓ DNS leak protection enabled")
            except Exception:
                pass
            self._flush_dns()
            if self._client_was_running and self._restart_client():
                results.append("✓ GUI client synced")
        return {"ok": any_ok, "message": " | ".join(results)}

    def _is_client_running(self):
        client_path = self._find_vpn_client()
        if not client_path:
            return False
        client_exe = os.path.basename(client_path).lower()
        try:
            r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {client_exe}", "/NH"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            return client_exe in r.stdout.lower()
        except Exception:
            return False

    def _restart_client(self):
        targets = self._resolve_target_providers()
        if not targets:
            return False
        client_path = self._find_vpn_client()
        if not client_path:
            return False
        client_exe = os.path.basename(client_path).lower()
        try:
            subprocess.run(["taskkill", "/F", "/IM", client_exe], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
        time.sleep(1)
        try:
            subprocess.Popen(f'"{client_path}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.DETACHED_PROCESS)
            return True
        except Exception:
            pass
        try:
            subprocess.Popen(['powershell', '-Command', f'Start-Process -FilePath "{client_path}"'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            return False

    def _pid_name_map(self):
        mapping = {}
        try:
            r = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in r.stdout.splitlines():
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    name = parts[0].strip('"')
                    pid_str = parts[1].strip('"')
                    if pid_str.isdigit():
                        mapping[int(pid_str)] = name
        except Exception:
            pass
        return mapping

    def _get_process_name(self, pid, mapping=None):
        if not pid:
            return ""
        if mapping and pid in mapping:
            return mapping[pid]
        try:
            return psutil.Process(pid).name()
        except Exception:
            return f"(pid:{pid})"

    def _flush_dns(self):
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            return False

    def _get_vpn_adapter_name(self):
        adapters = self._active_vpn_adapters()
        if adapters:
            return adapters[0]
        cfg = self.vpn_config.get("provider", "").strip().lower()
        for pid, prov in PROVIDERS.items():
            if pid in cfg or cfg in pid:
                kw = "|".join(prov.keywords) or pid
                try:
                    r = subprocess.run(f'netsh interface show interface | findstr /i "{kw}"', shell=True, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                    for line in r.stdout.splitlines():
                        parts = line.split()
                        if len(parts) >= 4:
                            return parts[-1]
                except Exception:
                    pass
        return None

    # --- Killswitch (via provider's on_killswitch) ---

    def _killswitch_available(self):
        for pid, prov in PROVIDERS.items():
            if not prov.killswitch_cli:
                continue
            if self._detect_cli(provider_hint=pid):
                return True
        return False

    def toggle_killswitch(self, payload=None):
        enabled = payload and payload.get("enabled", False)
        if enabled:
            result = self._enable_killswitch()
        else:
            result = self._disable_killswitch()
        real_state = self._detect_killswitch_state()
        self.vpn_config["killswitch"] = bool(real_state)
        self._save_vpn_config()
        return {"value": result}

    def get_killswitch(self):
        return {"value": {
            "enabled": self._detect_killswitch_state(),
            "available": self._killswitch_available()
        }}

    def _detect_killswitch_state(self):
        for pid, prov in PROVIDERS.items():
            if not prov.killswitch_cli or not prov.killswitch_status:
                continue
            cli_path = self._detect_cli(provider_hint=pid)
            if not cli_path:
                continue
            try:
                r = subprocess.run([cli_path] + prov.killswitch_status, capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                output = r.stdout.lower()
                if prov.killswitch_keyword in output:
                    return True
                inverted = prov.killswitch_keyword.replace(": on", ": off")
                if inverted in output:
                    return False
            except Exception:
                pass
        stored = self.vpn_config.get("killswitch", False)
        if isinstance(stored, str):
            return stored.lower() == "true"
        return bool(stored)

    def _enable_killswitch(self):
        parts = []
        for pid, prov in PROVIDERS.items():
            if not prov.killswitch_cli:
                continue
            cli_path = self._detect_cli(provider_hint=pid)
            if not cli_path:
                continue
            ok, msg = prov.on_killswitch("on", cli_path, self)
            parts.append(msg)
        return " | ".join(parts) if parts else "No providers with killswitch"

    def _disable_killswitch(self):
        parts = []
        for pid, prov in PROVIDERS.items():
            if not prov.killswitch_cli:
                continue
            cli_path = self._detect_cli(provider_hint=pid)
            if not cli_path:
                continue
            ok, msg = prov.on_killswitch("off", cli_path, self)
            parts.append(msg)
        return " | ".join(parts) if parts else "No providers with killswitch"

    # --- DNS ---

    def set_vpn_dns(self, payload=None):
        adapter = self._get_vpn_adapter_name()
        if not adapter:
            return {"value": "Could not detect VPN adapter"}
        parts = []
        try:
            subprocess.run(["netsh", "interface", "ip", "set", "dns", f'name="{adapter}"', "static", "1.1.1.1", "primary"], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            subprocess.run(["netsh", "interface", "ip", "add", "dns", f'name="{adapter}"', "1.0.0.1", "index=2"], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            parts.append(f"Cloudflare en {adapter}")
            subprocess.run(["reg", "add", "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\DNSClient", "/v", "DisableSmartNameResolution", "/t", "REG_DWORD", "/d", "1", "/f"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            parts.append("SmartMultiHomedNameResolution OFF")
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            parts.append("DNS cache flushed")
            return {"value": " | ".join(parts)}
        except Exception as e:
            return {"value": f"Error: {e}"}

    def dns_leak(self):
        try:
            vpn_ip = requests.get("https://api.ipify.org", timeout=5).text.strip()

            dns_ip = None
            try:
                r = subprocess.run(
                    ['nslookup', 'myip.opendns.com', 'resolver1.opendns.com'],
                    capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW
                )
                for line in r.stdout.splitlines():
                    if line.strip().startswith("Address"):
                        parts = line.split(":", 1)
                        if len(parts) >= 2:
                            ip = parts[-1].strip()
                            if ip and ip[0].isdigit():
                                dns_ip = ip
            except Exception:
                pass

            leak = (dns_ip is not None and dns_ip != vpn_ip) if dns_ip else None

            dns_servers = []
            try:
                r = subprocess.run(["netsh", "interface", "ip", "show", "dns"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                lines = r.stdout.splitlines()
                current_iface = ""
                for line in lines:
                    stripped = line.strip()
                    if "DNS" not in stripped and ":" in stripped and "nombre" not in stripped.lower():
                        parts = stripped.split(":", 1)
                        if len(parts) >= 2 and parts[-1].strip():
                            current_iface = parts[-1].strip()
                    if "DNS" in stripped and ":" in stripped:
                        parts = stripped.split(":", 1)
                        if len(parts) >= 2:
                            val = parts[-1].strip()
                            if val and val[0].isdigit() and val != "0.0.0.0":
                                dns_servers.append({"interface": current_iface, "dns": val})
            except Exception:
                pass

            return {"value": {
                "value": f"IP real: {vpn_ip} | DNS resuelve: {dns_ip or '?'}",
                "leak": leak, "real_ip": vpn_ip,
                "dns_resolved": dns_ip or "?",
                "dns_match": dns_ip == vpn_ip if dns_ip else None,
                "dns_servers": dns_servers[:5],
                "details": (
                    "✓ DNS secure" if (dns_ip and dns_ip == vpn_ip) else
                    "✗ POSSIBLE DNS LEAK" if leak else
                    "⚠ Could not fully verify"
                )
            }}
        except Exception as e:
            return {"value": f"Error: {e}"}

    # --- IP, Status, Config ---

    def get_ip(self, force=False):
        now = time.time()
        if not force and self._ip_cache and now - self._ip_cache_time < 5:
            return {"value": self._ip_cache}
        try:
            ip = requests.get("https://api.ipify.org", timeout=5).text
            self._ip_cache = ip
            self._ip_cache_time = now
            return {"value": ip}
        except Exception:
            return {"value": self._ip_cache or "No internet"}

    def _resolve_provider_name(self, adapters=None):
        if adapters is None:
            adapters = self._active_vpn_adapters()
        if not adapters:
            return self.vpn_config.get("provider", "") or "VPN"
        adapter_text = " ".join(a.lower() for a in adapters)
        for pid, prov in PROVIDERS.items():
            if any(kw in adapter_text for kw in prov.keywords):
                return pid.capitalize()
        return self.vpn_config.get("provider", "") or "VPN"

    def check_vpn(self):
        now = time.time()
        if self._vpn_check_cache and now - self._vpn_check_cache_time < 5:
            return self._vpn_check_cache
        adapters = self._active_vpn_adapters()
        if adapters:
            provider = self._resolve_provider_name(adapters)
            result = {"value": {"status": "ok", "text": f"{provider} active: {', '.join(adapters[:2])}"}}
            self._vpn_check_cache = result
            self._vpn_check_cache_time = now
            return result
        try:
            ip, data = self._public_ip_info()
            org = data.get("org", "")
            if any(kw in org.lower() for kw in ["vpn", "proxy", "hosting", "datacenter"]):
                result = {"value": {"status": "ok", "text": f"VPN/Proxy detected: {org[:40]}"}}
            else:
                result = {"value": {"status": "warn", "text": f"No VPN: {data.get('city', '?')}, {data.get('country', '?')}"}}
            self._vpn_check_cache = result
            self._vpn_check_cache_time = now
            return result
        except Exception:
            return {"value": {"status": "warn", "text": "VPN disconnected"}}

    def get_vpn_status(self):
        adapters = self._active_vpn_adapters()
        status = self.check_vpn().get("value", {})
        return {"value": {
            "active": bool(adapters) or "detected" in status.get("text", "").lower(),
            "status": status.get("status", "warn"),
            "text": status.get("text", "VPN disconnected"),
            "adapters": adapters,
            "provider": self._resolve_provider_name(adapters),
            "last_action": self.vpn_config.get("last_action", "")
        }}

    def get_vpn_config(self):
        return {"value": self.vpn_config}

    def save_vpn_config(self, payload=None):
        payload = payload or {}
        for key in ("provider", "connect_command", "disconnect_command", "adapter_keywords"):
            if key in payload:
                val = payload[key]
                if key == "adapter_keywords" and isinstance(val, list):
                    self.vpn_config[key] = ",".join(kw.strip() for kw in val if kw.strip())
                else:
                    self.vpn_config[key] = str(val or "").strip()
        target = (payload.get("target_provider") or "").strip()
        if target:
            self.vpn_config["provider"] = target
        self._save_vpn_config()
        return {"value": {"saved": True, "config": self.vpn_config}}

    def get_available_providers(self):
        installed = self._detect_installed_vpns()
        active = self._detect_active_providers()
        cfg = self.vpn_config.get("provider", "").strip().lower()
        result = []
        for pid in sorted(installed):
            prov = PROVIDERS.get(pid)
            if not prov:
                continue
            cli_path = self._detect_cli(provider_hint=pid)
            result.append({
                "id": pid, "name": pid.capitalize(),
                "has_cli": cli_path is not None,
                "active": pid in active,
                "configured": pid == cfg or cfg in pid,
                "cli_connect": prov.cli_connect,
                "cli_disconnect": prov.cli_disconnect,
            })
        return {"value": result}

    def connect_vpn(self, payload=None):
        if payload:
            target = (payload.get("target_provider") or "").strip()
            if target:
                self.vpn_config["provider"] = target
            self.save_vpn_config(payload)
        result = self._universal_connect()
        self.vpn_config["last_action"] = f"connect {time.strftime('%Y-%m-%d %H:%M:%S')}: {result['message']}"
        self._save_vpn_config()
        return {"value": {**result, "status": self.get_vpn_status()["value"]}}

    def disconnect_vpn(self, payload=None):
        if payload:
            target = (payload.get("target_provider") or "").strip()
            if target:
                self.vpn_config["provider"] = target
            self.save_vpn_config(payload)
        result = self._universal_disconnect()
        self.vpn_config["last_action"] = f"disconnect {time.strftime('%Y-%m-%d %H:%M:%S')}: {result['message']}"
        self._save_vpn_config()
        return {"value": {**result, "status": self.get_vpn_status()["value"]}}

    def vpn_control(self):
        return self.get_vpn_status()

    def force_ip(self):
        return self.get_ip(force=True)

    def get_open_ports(self):
        now = time.time()
        if self._ports_cache and now - self._ports_cache_time < 15:
            return {"value": self._ports_cache}
        common = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 993, 995, 1433, 3306, 3389, 5432, 6379, 8080, 8443, 27017]
        host = "127.0.0.1"
        results = []
        def _scan_port(port):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.3)
                r = s.connect_ex((host, port))
                s.close()
                if r == 0:
                    return port
            except:
                pass
            return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_scan_port, p): p for p in common}
            for future in concurrent.futures.as_completed(futures, timeout=5):
                port = future.result()
                if port is not None:
                    results.append({"label": str(port), "value": "OPEN"})
        results.sort(key=lambda x: int(x["label"]))
        self._ports_cache = results
        self._ports_cache_time = now
        return {"value": results}

    def get_connections(self):
        if not HAS_PSUTIL:
            return {"value": "psutil no instalado"}
        lines = []
        try:
            conns = psutil.net_connections(kind="all")
            MAX = 120
            for i, c in enumerate(sorted(conns, key=lambda x: (x.type, x.laddr.port if x.laddr else 0))):
                if i >= MAX:
                    lines.append(f"... and {len(conns) - MAX} more connections")
                    break
                proto = "TCP" if c.type == socket.SOCK_STREAM else ("UDP" if c.type == socket.SOCK_DGRAM else str(c.type))
                laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-"
                raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
                state = c.status if c.status else "-"
                pname = ""
                if c.pid:
                    try:
                        p = psutil.Process(c.pid)
                        pname = f"{p.name()} ({c.pid})"
                    except:
                        pname = f"({c.pid})"
                lines.append("{:<7} {:<22} {:<22} {:<12} {}".format(proto, laddr, raddr, state, pname))
        except Exception as e:
            return {"value": f"Error reading connections: {e}"}
        if not lines:
            return {"value": "No connections found"}
        header = "{:<7} {:<22} {:<22} {:<12} {}".format("Proto", "Local", "Remote", "State", "Process")
        sep = "-" * 90
        return {"value": "\n".join([header, sep] + lines)}

    def get_incoming(self):
        if not HAS_PSUTIL:
            return {"value": []}
        conns = []
        pid_map = self._pid_name_map()
        try:
            for c in psutil.net_connections(kind="all"):
                if c.raddr:
                    continue
                l_ip = c.laddr.ip if c.laddr else ""
                l_port = c.laddr.port if c.laddr else 0
                if l_ip == "127.0.0.1" and l_port == 5000:
                    continue
                proto = "TCP" if c.type == socket.SOCK_STREAM else ("UDP" if c.type == socket.SOCK_DGRAM else str(c.type))
                conns.append({
                    "proto": proto,
                    "local": f"{l_ip}:{l_port}" if c.laddr else "-",
                    "state": c.status or "-",
                    "process": self._get_process_name(c.pid, pid_map),
                    "pid": c.pid or 0
                })
        except Exception:
            pass
        return {"value": conns}

    def get_outgoing(self):
        if not HAS_PSUTIL:
            return {"value": []}
        self_count = 0
        conns = []
        pid_map = self._pid_name_map()
        try:
            for c in psutil.net_connections(kind="all"):
                if not c.raddr:
                    continue
                l_ip = c.laddr.ip if c.laddr else ""
                r_ip = c.raddr.ip
                r_port = c.raddr.port
                if r_ip == "127.0.0.1" and r_port == 5000:
                    self_count += 1
                    continue
                if l_ip == "127.0.0.1" and c.laddr and c.laddr.port == 5000:
                    self_count += 1
                    continue
                proto = "TCP" if c.type == socket.SOCK_STREAM else ("UDP" if c.type == socket.SOCK_DGRAM else str(c.type))
                conns.append({
                    "proto": proto,
                    "local": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-",
                    "remote": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-",
                    "state": c.status or "-",
                    "process": self._get_process_name(c.pid, pid_map),
                    "pid": c.pid or 0
                })
        except Exception:
            pass
        return {"value": conns, "_self_count": self_count}

    def get_network_inspector(self):
        open_ports_data = self.get_open_ports().get("value", [])
        open_ports = [p["label"] for p in open_ports_data if p.get("value") == "OPEN"]

        incoming = []
        outgoing = []
        self_count = 0

        if HAS_PSUTIL:
            try:
                conns = psutil.net_connections(kind="all")
                for c in sorted(conns, key=lambda x: (x.type, x.laddr.port if x.laddr else 0)):
                    proto = "TCP" if c.type == socket.SOCK_STREAM else ("UDP" if c.type == socket.SOCK_DGRAM else str(c.type))
                    laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-"
                    raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
                    state = c.status if c.status else "-"
                    pname = ""
                    pid = c.pid or 0
                    if c.pid:
                        try:
                            p = psutil.Process(c.pid)
                            pname = f"{p.name()}"
                        except:
                            pname = f"(pid:{c.pid})"

                    is_self = False
                    if c.raddr:
                        r_ip = c.raddr.ip
                        r_port = c.raddr.port
                        l_ip = c.laddr.ip if c.laddr else ""
                        if r_ip == "127.0.0.1" and r_port == 5000:
                            is_self = True
                        if l_ip == "127.0.0.1" and c.laddr and c.laddr.port == 5000:
                            is_self = True

                    if is_self:
                        self_count += 1
                        continue

                    entry = {
                        "proto": proto, "local": laddr, "remote": raddr,
                        "state": state, "process": pname, "pid": pid
                    }
                    if c.raddr:
                        outgoing.append(entry)
                    else:
                        incoming.append(entry)
            except Exception:
                pass

        return {"value": {
            "open_ports": open_ports,
            "incoming": incoming,
            "outgoing": outgoing,
            "total_incoming": len(incoming),
            "total_outgoing": len(outgoing),
            "self_connections": self_count
        }}

