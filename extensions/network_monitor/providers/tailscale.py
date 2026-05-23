"""Tailscale — Zero-config VPN. No CLI connect/disconnect. Skip rasdial."""
from .base import BaseProvider

class TailscaleProvider(BaseProvider):
    id = "tailscale"; name = "Tailscale"
    keywords = ["tailscale"]
    tunnel_services = ["Tailscale"]
    tunnel_procs = []; all_procs = ["tailscale.exe"]
    client_names = ["tailscale.exe"]
    skip_rasdial = True
