import subprocess


class BaseProvider:
    id = ""
    name = ""
    keywords = []
    tunnel_services = []
    app_services = []
    tunnel_procs = []
    all_procs = []
    cli_name = ""
    cli_connect = []
    cli_disconnect = []
    client_names = []
    skip_rasdial = False
    skip_cli_connect = False
    killswitch_cli = ""
    killswitch_on = []
    killswitch_off = []
    killswitch_status = []
    killswitch_keyword = ""

    def on_connect(self, extension):
        return []

    def on_disconnect(self, extension):
        return []

    def on_killswitch(self, action, cli_path, extension):
        if not self.killswitch_cli or not getattr(self, f"killswitch_{action}", []):
            return False, f"{self.id}: killswitch not available via CLI"
        try:
            r = subprocess.run([cli_path] + getattr(self, f"killswitch_{action}"), capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                return True, f"{self.id}: killswitch {'enabled' if action == 'on' else 'disabled'}"
            return False, f"{self.id}: {r.stderr.strip() or r.stdout.strip()[:100]}"
        except Exception as e:
            return False, f"{self.id}: {e}"

    def status(self, extension):
        adapters = extension._active_vpn_adapters()
        if any(kw in " ".join(a.lower() for a in adapters) for kw in self.keywords):
            return "ok"
        return "warn"
