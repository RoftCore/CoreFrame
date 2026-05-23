from .base import BaseProvider


class NordProvider(BaseProvider):
    id = "nord"
    name = "NordVPN"
    keywords = ["nord"]
    tunnel_services = ["NordVPN"]
    tunnel_procs = []
    all_procs = ["nordvpn.exe"]
    cli_name = "nordvpn.exe"
    cli_connect = ["-c", "-g", "The Fastest"]
    cli_disconnect = ["-d"]
    client_names = ["nordvpn.exe"]
    _cli_search_dirs = [r"C:\Program Files\NordVPN"]
