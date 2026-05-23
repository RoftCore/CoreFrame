from .base import BaseProvider

class WireGuardProvider(BaseProvider):
    id = "wireguard"; name = "WireGuard"
    keywords = ["wireguard"]
    tunnel_services = ["WireGuardTunnel", "WireGuardTunnel$"]
    tunnel_procs = ["wireguard.exe", "wintun.dll"]
    all_procs = ["wireguard.exe", "wintun.dll"]
    client_names = ["wireguard.exe"]
    _cli_search_dirs = [r"C:\Program Files\WireGuard"]
