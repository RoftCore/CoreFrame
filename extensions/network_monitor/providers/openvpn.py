from .base import BaseProvider

class OpenvpnProvider(BaseProvider):
    id = "openvpn"; name = "OpenVPN"
    keywords = ["openvpn", "tun", "tap"]
    tunnel_procs = ["openvpn.exe", "openvpn-gui.exe"]
    all_procs = ["openvpn.exe", "openvpn-gui.exe"]
    client_names = ["openvpn-gui.exe"]
    skip_rasdial = True
    _cli_search_dirs = [r"C:\Program Files\OpenVPN\bin"]
