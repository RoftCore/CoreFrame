from .base import BaseProvider


class MullvadProvider(BaseProvider):
    id = "mullvad"
    name = "Mullvad"
    keywords = ["mullvad"]
    tunnel_services = ["MullvadVPN"]
    tunnel_procs = []
    all_procs = ["mullvad-daemon.exe", "mullvad-gui.exe"]
    cli_name = "mullvad.exe"
    cli_connect = ["relay", "set", "location", "any"]
    cli_disconnect = ["relay", "disconnect"]
    client_names = ["mullvad.exe"]
    skip_rasdial = True
    _cli_search_dirs = [r"C:\Program Files\Mullvad VPN"]
