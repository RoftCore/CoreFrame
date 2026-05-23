import os

from .base import BaseProvider


class ProtonProvider(BaseProvider):
    id = "proton"
    name = "Proton VPN"
    keywords = ["proton"]
    tunnel_services = ["ProtonVPN WireGuard"]
    app_services = ["ProtonVPN Service"]
    tunnel_procs = ["protonvpn.wireguardservice.exe"]
    all_procs = ["protonvpn.wireguardservice.exe", "protonvpn.client.exe", "protonvpnservice.exe", "protonvpn.exe", "protonvpn-service.exe"]
    cli_name = "protonvpn-cli.exe"
    cli_connect = ["connect", "--fastest"]
    cli_disconnect = ["disconnect"]
    client_names = ["protonvpn.client.exe", "protonvpn.exe"]
    killswitch_cli = "protonvpn-cli.exe"
    killswitch_on = ["killswitch", "on"]
    killswitch_off = ["killswitch", "off"]
    killswitch_status = ["status"]
    killswitch_keyword = "kill switch: on"
    _cli_search_dirs = [
        r"C:\Program Files\Proton\VPN\Bin",
        r"C:\Program Files\Proton\VPN",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Proton\Proton VPN"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Proton\Proton VPN"),
    ]
