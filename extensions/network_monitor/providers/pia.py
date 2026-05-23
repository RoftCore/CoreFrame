from .base import BaseProvider

class PIAProvider(BaseProvider):
    id = "pia"; name = "Private Internet Access"
    keywords = ["pia"]
    tunnel_services = ["PIA VPN Service"]
    tunnel_procs = []; all_procs = ["pia-client.exe"]
