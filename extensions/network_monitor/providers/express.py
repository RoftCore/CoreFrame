from .base import BaseProvider

class ExpressProvider(BaseProvider):
    id = "express"; name = "ExpressVPN"
    keywords = ["express"]
    tunnel_services = ["ExpressVPN"]
    tunnel_procs = []; all_procs = ["expressvpntray.exe"]
